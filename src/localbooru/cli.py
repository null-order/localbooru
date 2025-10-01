"""Command-line entry point for localbooru."""
from __future__ import annotations

import argparse
import logging
import socket
import threading
from contextlib import closing
from pathlib import Path
from typing import Optional

from .config import LocalBooruConfig

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LocalBooru – NovelAI browser with CLIP search")
    parser.add_argument("--root", default=".", help="Root directory to scan for NovelAI PNGs")
    parser.add_argument("--db", default="gallery.db", help="Path to SQLite database")
    parser.add_argument("--thumb-cache", help="Path for thumbnail cache")
    parser.add_argument("--thumb-size", type=int, default=512, help="Maximum thumbnail size in pixels")
    parser.add_argument("--watch", action="store_true", help="Enable background rescanner")
    parser.add_argument("--rescan-interval", type=int, default=600, help="Interval for rescans when watch mode enabled")
    parser.add_argument("--no-thumbs", action="store_true", help="Disable thumbnail generation")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind HTTP server")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind HTTP server")
    parser.add_argument("--clip-device", default="cpu", help="Device string for CLIP model (cpu/cuda)")
    parser.add_argument("--clip-batch-size", type=int, default=8, help="Image batch size for CLIP embedding computation")
    parser.add_argument("--no-clip", action="store_true", help="Disable CLIP indexing and search features")
    parser.add_argument("--clip-model-name", default="ViT-B-32-quickgelu", help="OpenCLIP model name")
    parser.add_argument("--clip-checkpoint", default="openai", help="OpenCLIP checkpoint name")
    parser.add_argument("--no-webview", action="store_true", help="Do not launch embedded webview window")
    parser.add_argument("--no-ui", action="store_true", help="Run without opening a browser window")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    parser.add_argument("--extra-root", action="append", help="Additional directories to include in scans")
    parser.add_argument("--scan-only", action="store_true", help="Run a single scan and exit")
    parser.add_argument("--clip-only", action="store_true", help="Rebuild CLIP embeddings and exit")
    parser.add_argument("--status", action="store_true", help="Print CLIP/scan status and exit")
    return parser


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )


def find_free_port(host: str, port: int) -> int:
    if port != 0:
        return port
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = LocalBooruConfig.from_args(args)
    setup_logging(config.log_level)

    config.port = find_free_port(config.host, config.port)

    LOGGER.info("localbooru starting", extra={"port": config.port, "root": str(config.root)})

    # Deferred imports to avoid pulling heavy dependencies for simple status calls later.
    from . import database
    from .scanner import Scanner
    from .server import run_server
    from .clip import ClipIndexer, ClipProgress

    Path(config.db_path).parent.mkdir(parents=True, exist_ok=True)
    Path(config.thumb_cache).mkdir(parents=True, exist_ok=True)

    db = database.LocalBooruDatabase(config.db_path)

    progress = ClipProgress(model_key=config.clip_model_key)
    clip_indexer: Optional[ClipIndexer] = None

    if config.clip_enabled:
        clip_indexer = ClipIndexer(
            db=db,
            config=config,
            progress=progress,
        )

    scanner = Scanner(config=config, db=db, clip_progress=progress)

    if args.status:
        status = progress.snapshot(db)
        print(status)
        return 0

    if args.scan_only:
        scanner.run_once()
        if clip_indexer:
            clip_indexer.process_until_empty()
        return 0

    if args.clip_only:
        if clip_indexer:
            clip_indexer.process_until_empty()
        else:
            LOGGER.warning("CLIP indexing disabled; nothing to do")
        return 0

    scanner.run_once()

    if config.clip_enabled:
        total, completed, processing = db.clip_progress_counts(config.clip_model_key)
        progress.total = total
        progress.completed = completed
        progress.processing = processing
        progress.queued = max(total - completed - processing, 0)

    server_thread = threading.Thread(
        target=run_server,
        kwargs={"config": config, "db": db, "scanner": scanner, "progress": progress, "clip_indexer": clip_indexer},
        daemon=True,
    )
    server_thread.start()

    if clip_indexer:
        clip_indexer.start()

    if config.watch:
        scanner.start()

    if not config.no_ui:
        try:
            from .webview_app import launch_webview

            launch_webview(config)
        except Exception as exc:  # pragma: no cover - webview optional path
            LOGGER.warning("unable to launch webview: %s", exc)

    try:
        server_thread.join()
    except KeyboardInterrupt:
        LOGGER.info("Shutting down...")

    if clip_indexer:
        clip_indexer.stop()
        clip_indexer.join()
    if config.watch:
        scanner.stop()
        scanner.join()

    db.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
