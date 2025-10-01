"""Filesystem scanner for NovelAI PNGs."""
from __future__ import annotations

import logging
import threading
from typing import Optional

from .config import LocalBooruConfig
from .clip import ClipProgress
from .database import LocalBooruDatabase
from .ingestion import scan_pngs


LOGGER = logging.getLogger(__name__)

class Scanner(threading.Thread):
    """Background rescanner thread (stub)."""

    def __init__(self, config: LocalBooruConfig, db: LocalBooruDatabase, clip_progress: ClipProgress):
        super().__init__(daemon=True)
        self.config = config
        self.db = db
        self.clip_progress = clip_progress
        self._stop_event = threading.Event()
        self._initial_run_complete = False

    def run_once(self) -> None:
        LOGGER.info("Running filesystem scan for %s", self.config.root)
        scan_pngs(self.db, self.config)
        LOGGER.info("Scan complete")
        self._initial_run_complete = True

    def run(self) -> None:  # pragma: no cover - background thread
        while not self._stop_event.is_set():
            if self._initial_run_complete:
                if not self.config.watch:
                    break
                if self._stop_event.wait(self.config.rescan_interval):
                    break
            self.run_once()
            if not self.config.watch:
                break

    def stop(self) -> None:
        self._stop_event.set()

    def join(self, timeout: Optional[float] = None) -> None:
        super().join(timeout)
