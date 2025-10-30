"""Filesystem watch helpers for LocalBooru."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .config import LocalBooruConfig
from .ingestion import IMAGE_PATTERNS
from .scanner import Scanner

LOGGER = logging.getLogger(__name__)

# Extract supported extensions from IMAGE_PATTERNS
SUPPORTED_EXTENSIONS = {pattern.lower().replace("*", "") for pattern in IMAGE_PATTERNS}

try:  # pragma: no cover - optional watchdog dependency
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer
except ModuleNotFoundError:  # pragma: no cover - fallback path
    FileSystemEvent = object  # type: ignore[assignment]

    class FileSystemEventHandler:  # type: ignore[override]
        """Fallback stub when watchdog is unavailable."""

        pass

    Observer = None  # type: ignore[assignment]


class _WatchdogEventHandler(FileSystemEventHandler):  # pragma: no cover - watchdog path
    def __init__(self, scanner: Scanner) -> None:
        super().__init__()
        self._scanner = scanner

    def _handle_event(
        self, path: Optional[str], is_directory: bool, event_type: str
    ) -> None:
        if is_directory:
            return
        if not path:
            return
        suffix = Path(path).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            return
        p = Path(path)
        LOGGER.debug("Filesystem change detected for %s: %s", path, event_type)
        if event_type == "deleted":
            self._scanner.mark_deleted(p)
        else:
            self._scanner.incremental_ingest(p)

    def on_created(self, event: FileSystemEvent) -> None:
        self._handle_event(
            getattr(event, "src_path", None),
            getattr(event, "is_directory", False),
            "created",
        )

    def on_modified(self, event: FileSystemEvent) -> None:
        self._handle_event(
            getattr(event, "src_path", None),
            getattr(event, "is_directory", False),
            "modified",
        )

    def on_deleted(self, event: FileSystemEvent) -> None:
        self._handle_event(
            getattr(event, "src_path", None),
            getattr(event, "is_directory", False),
            "deleted",
        )

    def on_moved(self, event: FileSystemEvent) -> None:
        self._handle_event(
            getattr(event, "dest_path", None),
            getattr(event, "is_directory", False),
            "moved_dest",
        )
        self._handle_event(
            getattr(event, "src_path", None),
            getattr(event, "is_directory", False),
            "deleted",
        )


class DirectoryWatcher:
    """Bridge between watchdog observers and the scanner trigger."""

    def __init__(self, config: LocalBooruConfig, scanner: Scanner) -> None:
        self._config = config
        self._scanner = scanner
        self._observer: Optional[Observer] = None
        self._handler: Optional[_WatchdogEventHandler] = None
        self._scheduled = 0

    @property
    def is_running(self) -> bool:
        return bool(self._observer)

    def start(self) -> None:
        if Observer is None:
            LOGGER.debug("watchdog Observer unavailable; skipping filesystem watcher")
            return
        handler = _WatchdogEventHandler(self._scanner)
        observer = Observer()
        scheduled = 0
        for root in self._config.roots:
            try:
                observer.schedule(handler, str(root), recursive=True)
                scheduled += 1
            except FileNotFoundError:
                LOGGER.warning("Watch root %s does not exist yet; skipping", root)
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning("Unable to watch %s: %s", root, exc)
        if scheduled == 0:
            LOGGER.info(
                "Filesystem watching disabled; no valid directories were scheduled"
            )
            return
        observer.start()
        LOGGER.info("Started filesystem watcher for %d directories", scheduled)
        self._observer = observer
        self._handler = handler
        self._scheduled = scheduled

    def stop(self) -> None:
        if not self._observer:
            return
        self._observer.stop()
        self._observer.join(timeout=5)
        LOGGER.info("Stopped filesystem watcher")
        self._observer = None
        self._handler = None
        self._scheduled = 0

    @property
    def has_directories(self) -> bool:
        return self._scheduled > 0


def create_directory_watcher(
    config: LocalBooruConfig, scanner: Scanner
) -> Optional[DirectoryWatcher]:
    if Observer is None:
        LOGGER.info(
            "watchdog is not installed; falling back to interval rescans for watch mode"
        )
        return None
    return DirectoryWatcher(config, scanner)
