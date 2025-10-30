"""Command-line entry point for localbooru."""

from __future__ import annotations

import argparse
import logging
import os
import socket
import threading
import webbrowser
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
import sys
from typing import Optional

from .config import (
    LocalBooruConfig,
    load_config_file,
    render_default_config_template,
)

LOGGER = logging.getLogger(__name__)


class _ScanProgressPrinter(threading.Thread):
    def __init__(self, progress: "ScanProgress", stream) -> None:
        super().__init__(daemon=True)
        self.progress = progress
        self.stream = stream
        self._stop_event = threading.Event()
        self._last_line_length = 0

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:  # pragma: no cover - terminal UX
        while not self._stop_event.is_set():
            self._render()
            if self._stop_event.wait(0.5):
                break
        self._render(final=True)

    def _render(self, final: bool = False) -> None:
        snapshot = self.progress.snapshot()
        total = snapshot.get("total") or 0
        processed = snapshot.get("processed") or 0
        errors = snapshot.get("errors") or 0
        state = snapshot.get("state") or "idle"
        rate = snapshot.get("rate_per_min") or 0.0
        eta = snapshot.get("eta_seconds")
        percent = (processed / total * 100.0) if total else 0.0
        if rate > 0.1:
            rate_display = f"{rate:.1f}/min"
        elif rate > 0:
            rate_display = f"{rate:.2f}/min"
        else:
            rate_display = ""
        eta_display = ""
        if isinstance(eta, (float, int)) and eta and eta > 0:
            eta_display = _format_eta(float(eta))
        parts = [
            "Scanning",
            f"{processed}/{total}" if total else str(processed),
            f"{percent:5.1f}%",
        ]
        if rate_display:
            parts.append(rate_display)
        if eta_display:
            parts.append(f"ETA {eta_display}")
        if errors:
            parts.append(f"errors:{errors}")
        if state == "complete" and not final:
            parts.append("[finalizing]")
        else:
            parts.append(f"[{state}]")
        line = " | ".join(parts)
        padded = line.ljust(self._last_line_length)
        self.stream.write(f"\r{padded}")
        self.stream.flush()
        self._last_line_length = len(line)
        if final:
            self.stream.write("\n")
            self.stream.flush()
            self._last_line_length = 0


def _format_eta(seconds: float) -> str:
    seconds = max(0.0, seconds)
    minutes, sec = divmod(int(seconds + 0.5), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{sec:02d}s"
    return f"{sec}s"


def _run_scan(
    scanner: "Scanner",
    scan_progress: "ScanProgress",
    *,
    show_progress: bool,
    stream=None,
) -> None:
    printer: Optional[_ScanProgressPrinter] = None
    if show_progress:
        printer = _ScanProgressPrinter(scan_progress, stream or sys.stderr)
        printer.start()
    try:
        scanner.run_once()
    finally:
        if printer is not None:
            printer.stop()
            printer.join()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="LocalBooru – NovelAI browser with CLIP search"
    )
    parser.add_argument(
        "--root",
        help="Root directory to scan for NovelAI PNGs (overrides config file)",
    )
    parser.add_argument(
        "--db",
        help="Path to SQLite database (overrides config file)",
    )
    parser.add_argument(
        "--thumb-cache",
        help="Path for thumbnail cache (default: XDG cache)",
        default=None,
    )
    parser.add_argument(
        "--thumb-size",
        type=int,
        default=None,
        help="Maximum thumbnail size in pixels (default: 512)",
    )
    parser.add_argument(
        "--watch", action="store_true", help="Enable background rescanner"
    )
    parser.add_argument(
        "--rescan-interval",
        type=int,
        default=None,
        help="Interval for rescans when watch mode enabled (seconds, default: 600)",
    )
    parser.add_argument(
        "--no-thumbs", action="store_true", help="Disable thumbnail generation"
    )
    parser.add_argument(
        "--host",
        help="Host to bind HTTP server (default: 127.0.0.1)",
        default=None,
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to bind HTTP server (default: 8000)",
    )
    parser.add_argument(
        "--clip-device",
        help="Device string for CLIP model (default: cpu)",
        default=None,
    )
    parser.add_argument(
        "--clip-batch-size",
        type=int,
        default=None,
        help="Image batch size for CLIP embedding computation (default: 8)",
    )
    parser.add_argument(
        "--no-clip",
        action="store_true",
        help="Disable CLIP indexing and search features",
    )
    parser.add_argument(
        "--clip-model-name",
        help="OpenCLIP model name (default: ViT-B-32-quickgelu)",
        default=None,
    )
    parser.add_argument(
        "--clip-checkpoint",
        help="OpenCLIP checkpoint name (default: openai)",
        default=None,
    )
    parser.add_argument(
        "--auto-tag-missing",
        dest="auto_tag_missing",
        action="store_true",
        default=None,
        help="Enable WD14 auto-tagging integration (default: enabled)",
    )
    parser.add_argument(
        "--no-auto-tag",
        dest="auto_tag_missing",
        action="store_false",
        help="Disable WD14 auto-tagging integration",
    )
    parser.add_argument(
        "--auto-tag-model",
        help="WD14 model to load when auto-tagging is enabled (default: ConvNextV2)",
        default=None,
    )
    parser.add_argument(
        "--auto-tag-general-threshold",
        type=float,
        default=None,
        help="Confidence threshold for WD14 general tags (default: 0.35)",
    )
    parser.add_argument(
        "--auto-tag-character-threshold",
        type=float,
        default=None,
        help="Confidence threshold for WD14 character tags (default: 0.85)",
    )
    parser.add_argument(
        "--auto-tag-mode",
        choices=["missing", "augment"],
        default=None,
        help="Control whether WD14 tags only fill gaps or also augment embedded metadata (default: augment)",
    )
    parser.add_argument(
        "--auto-tag-background",
        dest="auto_tag_background",
        action="store_true",
        default=None,
        help="Queue auto-tagging jobs for background processing (default: enabled)",
    )
    parser.add_argument(
        "--no-auto-tag-background",
        dest="auto_tag_background",
        action="store_false",
        help="Run auto-tagging inline during ingestion",
    )
    parser.add_argument(
        "--auto-tag-batch-size",
        type=int,
        default=None,
        help="Number of auto-tagging jobs to process per batch when background mode is enabled (default: 4)",
    )
    parser.add_argument(
        "--webview",
        action="store_true",
        help="Launch the embedded pywebview window instead of opening the default browser",
    )
    parser.add_argument(
        "--no-ui", action="store_true", help="Run without opening a browser window"
    )
    parser.add_argument(
        "--log-level", help="Logging level (default: INFO)", default=None
    )
    parser.add_argument(
        "--extra-root",
        action="append",
        help="Additional directories to include in scans",
    )
    parser.add_argument(
        "--scan-only", action="store_true", help="Run a single scan and exit"
    )
    parser.add_argument(
        "--clip-only", action="store_true", help="Rebuild CLIP embeddings and exit"
    )
    parser.add_argument(
        "--config",
        help="Path to configuration file (JSON/TOML/YAML). Overrides may be provided by CLI flags.",
    )
    parser.add_argument(
        "--cwd",
        action="store_true",
        help="Use legacy cwd-relative defaults (ignore config files unless explicitly provided).",
    )
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print an annotated configuration template (TOML) and exit.",
    )
    parser.add_argument(
        "--service",
        action="store_true",
        help="Service mode: enable watch, disable UI launch, and prefer config defaults.",
    )
    parser.add_argument(
        "--status", action="store_true", help="Print CLIP/scan status and exit"
    )
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

    if getattr(args, "print_config", False):
        print(render_default_config_template())
        return 0

    use_cwd_mode = bool(getattr(args, "cwd", False))
    config_path_input = args.config or os.getenv("LOCALBOORU_CONFIG")
    config_path = None

    if use_cwd_mode:
        if config_path_input:
            LOGGER.error(
                "--cwd cannot be combined with --config or LOCALBOORU_CONFIG"
            )
            return 2
    else:
        if not config_path_input:
            default_config = Path.home() / ".localbooru.toml"
            if default_config.exists():
                config_path_input = str(default_config)
        config_path = config_path_input

    config_data = None
    loaded_config_path = None
    if config_path:
        loaded_config_path = Path(config_path).expanduser()
        try:
            config_data = load_config_file(loaded_config_path)
        except FileNotFoundError:
            LOGGER.error("Configuration file not found: %s", loaded_config_path)
            return 2
        except Exception as exc:
            LOGGER.error("Failed to load configuration %s: %s", loaded_config_path, exc)
            return 2
        if config_data is None:
            config_data = {}
        elif not isinstance(config_data, Mapping):
            LOGGER.error(
                "Configuration root must be a mapping; got %s", type(config_data).__name__
            )
            return 2
        loaded_config_path = loaded_config_path.resolve()
        LOGGER.info("Loaded configuration from %s", loaded_config_path)

    config = LocalBooruConfig.from_sources(
        args,
        file_options=config_data,
        config_path=loaded_config_path,
    )
    setup_logging(config.log_level)

    config.port = find_free_port(config.host, config.port)

    LOGGER.info(
        "localbooru starting",
        extra={
            "port": config.port,
            "roots": [str(path) for path in config.roots],
            "service": config.service_mode,
            "cwd_mode": use_cwd_mode,
        },
    )

    # Deferred imports to avoid pulling heavy dependencies for simple status calls later.
    from . import database
    from .auto_tagging import AutoTagIndexer, AutoTagProgress
    from .scanner import ScanProgress, Scanner
    from .server import create_http_server
    from .clip import ClipIndexer, ClipProgress
    from .watchers import create_directory_watcher


    Path(config.db_path).parent.mkdir(parents=True, exist_ok=True)
    Path(config.thumb_cache).mkdir(parents=True, exist_ok=True)

    db = database.LocalBooruDatabase(config.db_path)

    clip_reset = db.reset_stuck_clip_jobs(
        config.clip_model_key if config.clip_enabled else None
    )
    auto_reset = db.reset_stuck_auto_jobs()
    if clip_reset or auto_reset:
        LOGGER.info(
            "Reset stuck jobs",
            extra={
                "clip_requeued": clip_reset,
                "auto_requeued": auto_reset,
            },
        )

    progress = ClipProgress(model_key=config.clip_model_key)
    auto_progress = AutoTagProgress()
    clip_indexer: Optional[ClipIndexer] = None
    auto_indexer: Optional[AutoTagIndexer] = None

    if config.clip_enabled:
        clip_indexer = ClipIndexer(
            db=db,
            config=config,
            progress=progress,
        )

    if config.auto_tag_missing and config.auto_tag_background:
        auto_indexer = AutoTagIndexer(
            db=db,
            config=config,
            progress=auto_progress,
        )

    scan_progress = ScanProgress()
    scanner = Scanner(
        config=config, db=db, clip_progress=progress, scan_progress=scan_progress
    )
    directory_watcher = None

    if args.status:
        status = {
            "clip": progress.snapshot(db),
        }
        if config.auto_tag_missing:
            status["auto_tag"] = auto_progress.snapshot(db)
        total_images = db.connection.execute("SELECT COUNT(*) FROM images").fetchone()[0]
        rating_counts = db.rating_counts()
        status["rating"] = {
            "counts": rating_counts,
            "tagged": sum(rating_counts.values()),
            "total": total_images,
        }
        print(status)
        return 0

    if args.scan_only:
        _run_scan(
            scanner, scan_progress, show_progress=sys.stderr.isatty(), stream=sys.stderr
        )
        if clip_indexer:
            clip_indexer.process_until_empty()
        if auto_indexer:
            auto_indexer.process_until_empty()
        return 0

    if args.clip_only:
        if clip_indexer:
            clip_indexer.process_until_empty()
        else:
            LOGGER.warning("CLIP indexing disabled; nothing to do")
        return 0

    _run_scan(
        scanner,
        scan_progress,
        show_progress=(sys.stderr.isatty() and not args.status),
        stream=sys.stderr,
    )

    if config.clip_enabled:
        total, completed, processing, errors = db.clip_progress_counts(
            config.clip_model_key
        )
        effective_total = max(total - errors, 0)
        progress.total = total
        progress.completed = completed
        progress.processing = processing
        progress.error_count = errors
        progress.queued = max(effective_total - completed - processing, 0)

    if config.auto_tag_missing:
        auto_progress.refresh_from_db(db)

    httpd = create_http_server(
        config=config,
        db=db,
        scanner=scanner,
        progress=progress,
        clip_indexer=clip_indexer,
        auto_progress=auto_progress,
        auto_indexer=auto_indexer,
    )
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    LOGGER.info("HTTP server listening on http://%s:%d", config.host, config.port)

    if clip_indexer:
        clip_indexer.start()

    if auto_indexer:
        auto_indexer.start()

    if config.watch and directory_watcher is None:
        directory_watcher = create_directory_watcher(config, scanner)

    if config.watch:
        if directory_watcher:
            scanner.set_periodic_enabled(False)
        else:
            scanner.set_periodic_enabled(True)
        scanner.start()
        if directory_watcher:
            directory_watcher.start()

    app_url = f"http://{config.host}:{config.port}/"
    if not config.no_ui:
        if config.webview:
            try:
                from .webview_app import launch_webview

                launch_webview(config)
            except Exception as exc:  # pragma: no cover - webview optional path
                LOGGER.warning("unable to launch webview: %s", exc)
        else:
            try:
                webbrowser.open(app_url)
            except Exception as exc:  # pragma: no cover - optional
                LOGGER.warning("unable to open browser: %s", exc)

    try:
        while server_thread.is_alive():
            server_thread.join(timeout=0.5)
    except KeyboardInterrupt:
        LOGGER.info("Shutting down...")
    finally:
        try:
            httpd.shutdown()
        except Exception:  # pragma: no cover - defensive
            pass
        httpd.server_close()
        server_thread.join(timeout=2)

        if clip_indexer:
            clip_indexer.stop()
            clip_indexer.join()
        if auto_indexer:
            auto_indexer.stop()
            auto_indexer.join()
        if config.watch:
            if directory_watcher:
                directory_watcher.stop()
            scanner.stop()
            scanner.join()

        db.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
