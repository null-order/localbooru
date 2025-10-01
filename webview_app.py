"""Embedded webview launcher for localbooru."""
from __future__ import annotations

import logging

from .config import LocalBooruConfig

LOGGER = logging.getLogger(__name__)


def launch_webview(config: LocalBooruConfig) -> None:
    """Launch a frameless pywebview window pointing at the local server."""
    try:
        import webview  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        LOGGER.warning("pywebview not installed; skipping UI (%s)", exc)
        return

    url = f"http://{config.host}:{config.port}/"
    window = webview.create_window("LocalBooru", url=url, frameless=True)
    LOGGER.info("Opening pywebview window at %s", url)
    webview.start(gui=None, debug=False)
