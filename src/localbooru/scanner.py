"""Filesystem scanner for images."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from pathlib import Path

from .config import LocalBooruConfig
from .clip import ClipProgress
from .database import LocalBooruDatabase
from .ingestion import scan_images


LOGGER = logging.getLogger(__name__)


@dataclass
class ScanProgress:
    total: int = 0
    processed: int = 0
    errors: int = 0
    state: str = "idle"
    current_path: Optional[str] = None
    started_at: Optional[float] = None
    last_update: Optional[float] = None
    history: List[tuple[float, int]] = field(default_factory=list)
    _lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )

    def begin(self, total: int) -> None:
        with self._lock:
            self.total = total
            self.processed = 0
            self.errors = 0
            self.state = "running"
            self.current_path = None
            now = time.time()
            self.started_at = now
            self.last_update = now
            self.history.clear()
            self.history.append((now, 0))

    def step_start(self, path: str) -> None:
        with self._lock:
            self.current_path = path
            self.last_update = time.time()

    def step_finish(self, *, error: bool = False) -> None:
        with self._lock:
            self.processed += 1
            if error:
                self.errors += 1
            now = time.time()
            self.last_update = now
            self.history.append((now, self.processed))
            if len(self.history) > 120:
                self.history = self.history[-120:]

    def finish(self) -> None:
        with self._lock:
            self.state = "complete"
            self.current_path = None
            self.last_update = time.time()

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            data = {
                "total": self.total,
                "processed": self.processed,
                "errors": self.errors,
                "state": self.state,
                "current_path": self.current_path,
                "started_at": self.started_at,
                "last_update": self.last_update,
            }
            rate_per_min, eta_seconds = self._compute_rate_eta()
            data["rate_per_min"] = rate_per_min
            data["eta_seconds"] = eta_seconds
            return data

    def _compute_rate_eta(self) -> tuple[float, Optional[float]]:
        if len(self.history) < 2:
            return 0.0, None
        latest_time, latest_processed = self.history[-1]
        rate_per_min = 0.0
        eta_seconds = None
        for past_time, past_processed in reversed(self.history[:-1]):
            delta_count = latest_processed - past_processed
            delta_time = latest_time - past_time
            if delta_count > 0 and delta_time >= 0.5:
                rate_per_min = (delta_count / max(delta_time, 1e-6)) * 60.0
                break
        remaining = max(self.total - latest_processed, 0)
        if rate_per_min > 0 and remaining > 0:
            eta_seconds = (remaining / rate_per_min) * 60.0
        return rate_per_min, eta_seconds


class Scanner(threading.Thread):
    """Background rescanner thread with progress reporting."""

    def __init__(
        self,
        config: LocalBooruConfig,
        db: LocalBooruDatabase,
        clip_progress: ClipProgress,
        scan_progress: Optional[ScanProgress] = None,
    ):
        super().__init__(daemon=True)
        self.config = config
        self.db = db
        self.clip_progress = clip_progress
        self.scan_progress = scan_progress or ScanProgress()
        self._stop_event = threading.Event()
        self._initial_run_complete = False
        self._rescan_event = threading.Event()
        self._periodic_enabled = True

    def run_once(self) -> None:
        roots_display = ", ".join(str(path) for path in self.config.roots)
        LOGGER.info("Running filesystem scan for %s", roots_display)
        scan_images(self.db, self.config, progress=self.scan_progress)
        LOGGER.info(
            "Scan complete (%d processed, %d errors)",
            self.scan_progress.processed,
            self.scan_progress.errors,
        )
        self._initial_run_complete = True

    def run(self) -> None:  # pragma: no cover - background thread
        skip_initial_run = self._initial_run_complete
        while not self._stop_event.is_set():
            if skip_initial_run:
                skip_initial_run = False
            else:
                self._rescan_event.clear()
                self.run_once()
            if not self.config.watch or self._stop_event.is_set():
                break
            while not self._stop_event.is_set():
                if (
                    self._periodic_enabled
                    and self.config.rescan_interval
                    and self.config.rescan_interval > 0
                ):
                    triggered = self._rescan_event.wait(self.config.rescan_interval)
                else:
                    triggered = self._rescan_event.wait()
                if self._stop_event.is_set():
                    return
                if triggered:
                    self._rescan_event.clear()
                    break
                if (
                    self._periodic_enabled
                    and self.config.rescan_interval
                    and self.config.rescan_interval > 0
                ):
                    break

    def trigger_scan(self) -> None:
        """Request that the scanner perform another pass soon."""
        self._rescan_event.set()

    def incremental_ingest(self, path: Path) -> None:
        """Ingest a single file path incrementally."""
        from .ingestion import IngestAutoContext, ingest_path

        context: Optional[IngestAutoContext] = None
        if self.config.auto_tag_missing:
            jobs = self.db.load_auto_tag_jobs()
            tagged_ids = self.db.load_auto_tagged_ids()
            context = IngestAutoContext(jobs=jobs, auto_tagged=tagged_ids)

        try:
            image_id = ingest_path(self.db, self.config, path, context=context)
            if image_id is not None:
                LOGGER.info("Incrementally ingested %s (ID %d)", path, image_id)
        except Exception as exc:
            LOGGER.exception("Failed to incrementally ingest %s: %s", path, exc)

    def mark_deleted(self, path: Path) -> None:
        """Mark a file as deleted (for incremental deletions)."""
        try:
            rel_path = path.relative_to(self.config.root).as_posix()
        except ValueError:
            rel_path = path.as_posix()
        conn = self.db.connection
        with conn:
            deleted_count = conn.execute(
                "DELETE FROM images WHERE path = ?",
                (rel_path,),
            ).rowcount
        if deleted_count > 0:
            LOGGER.info("Marked %s as deleted (%d rows)", path, deleted_count)
        else:
            LOGGER.debug("No image found for deleted path %s", path)

    def stop(self) -> None:
        self._stop_event.set()
        self._rescan_event.set()

    def join(self, timeout: Optional[float] = None) -> None:
        super().join(timeout)

    def set_periodic_enabled(self, enabled: bool) -> None:
        self._periodic_enabled = bool(enabled)
        if enabled:
            self._rescan_event.set()
