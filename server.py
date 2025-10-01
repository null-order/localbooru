"""HTTP server for localbooru."""
from __future__ import annotations

import json
import logging
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from .clip import ClipIndexer, ClipProgress
from .config import LocalBooruConfig
from .database import LocalBooruDatabase
from .scanner import Scanner

LOGGER = logging.getLogger(__name__)


class LocalBooruRequestHandler(BaseHTTPRequestHandler):
    server_version = "LocalBooru/0.1"

    def do_GET(self) -> None:  # pragma: no cover - network path
        if self.path == "/api/status/clip":
            self._handle_clip_status()
            return
        if self.path == "/":
            self._serve_index()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:  # pragma: no cover - network path
        if self.path == "/api/clip/pause":
            self._handle_clip_control("pause")
            return
        if self.path == "/api/clip/resume":
            self._handle_clip_control("resume")
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def _handle_clip_status(self) -> None:
        progress: ClipProgress = self.server.progress  # type: ignore[attr-defined]
        payload = progress.snapshot(self.server.db)  # type: ignore[attr-defined]
        blob = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def _serve_index(self) -> None:
        index_file = Path(__file__).resolve().parent / "frontend" / "index.html"
        if not index_file.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "index.html missing")
            return
        data = index_file.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle_clip_control(self, action: str) -> None:
        clip_indexer: Optional[ClipIndexer] = self.server.clip_indexer  # type: ignore[attr-defined]
        if clip_indexer is None:
            self.send_error(HTTPStatus.BAD_REQUEST, "CLIP indexing disabled")
            return
        if action == "pause":
            clip_indexer.pause()
        elif action == "resume":
            clip_indexer.resume()
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # pragma: no cover - adjust logging
        LOGGER.info("%s - %s", self.address_string(), format % args)


class LocalBooruHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        RequestHandlerClass=LocalBooruRequestHandler,
        config: Optional[LocalBooruConfig] = None,
        db: Optional[LocalBooruDatabase] = None,
        scanner: Optional[Scanner] = None,
        progress: Optional[ClipProgress] = None,
        clip_indexer: Optional[ClipIndexer] = None,
    ) -> None:
        super().__init__(server_address, RequestHandlerClass)
        self.config = config
        self.db = db
        self.scanner = scanner
        self.progress = progress
        self.clip_indexer = clip_indexer


def run_server(
    config: LocalBooruConfig,
    db: LocalBooruDatabase,
    scanner: Scanner,
    progress: ClipProgress,
    clip_indexer: Optional[ClipIndexer],
) -> None:  # pragma: no cover - networking
    LOGGER.info("HTTP server listening on http://%s:%d", config.host, config.port)
    httpd = LocalBooruHTTPServer(
        (config.host, config.port),
        config=config,
        db=db,
        scanner=scanner,
        progress=progress,
        clip_indexer=clip_indexer,
    )
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
