"""Configuration helpers for localbooru."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from textwrap import dedent
from typing import Any, Mapping, Optional


def _default_state_dir() -> Path:
    state_root = Path(
        os.getenv("XDG_STATE_HOME", Path.home() / ".local" / "state")
    ).expanduser()
    return (state_root / "localbooru").resolve()


def _default_cache_dir() -> Path:
    cache_root = Path(
        os.getenv("XDG_CACHE_HOME", Path.home() / ".cache")
    ).expanduser()
    return (cache_root / "localbooru" / "thumbs").resolve()


def load_config_file(config_path: Path) -> Mapping[str, Any]:
    config_path = config_path.expanduser().resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    suffix = config_path.suffix.lower()
    if suffix in {".json"}:
        return json.loads(config_path.read_text(encoding="utf-8"))
    if suffix in {".toml", ".tml", ".ini"}:
        try:
            import tomllib  # type: ignore[attr-defined]
        except ModuleNotFoundError as exc:  # pragma: no cover - Python <3.11
            try:
                import tomli as tomllib  # type: ignore[import-not-found]
            except ModuleNotFoundError as fallback_exc:  # pragma: no cover
                raise RuntimeError(
                    "TOML configuration requested but neither tomllib nor tomli is available. "
                    "Install tomli or upgrade to Python 3.11+."
                ) from fallback_exc
        return tomllib.loads(config_path.read_text(encoding="utf-8"))
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except ModuleNotFoundError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "YAML configuration requested but PyYAML is not installed."
            ) from exc
        return yaml.safe_load(config_path.read_text(encoding="utf-8"))
    # Default to JSON parsing for unknown suffixes.
    return json.loads(config_path.read_text(encoding="utf-8"))


@dataclass
class LocalBooruConfig:
    root: Path
    db_path: Path
    thumb_cache: Path
    thumb_size: int = 512
    host: str = "127.0.0.1"
    port: int = 8000
    watch: bool = False
    rescan_interval: int = 600
    enable_thumbs: bool = True
    clip_device: str = "cpu"
    clip_batch_size: int = 8
    clip_enabled: bool = True
    clip_model_name: str = "ViT-B-32-quickgelu"
    clip_checkpoint: str = "openai"
    auto_tag_missing: bool = True
    auto_tag_model: str = "ConvNextV2"
    auto_tag_general_threshold: float = 0.35
    auto_tag_character_threshold: float = 0.85
    auto_tag_mode: str = "augment"
    auto_tag_background: bool = True
    auto_tag_batch_size: int = 4
    webview: bool = False
    no_ui: bool = False
    log_level: str = "INFO"
    extra_roots: list[Path] = field(default_factory=list)
    config_file: Optional[Path] = None
    service_mode: bool = False

    @classmethod
    def from_sources(
        cls,
        args: "argparse.Namespace",
        *,
        file_options: Optional[Mapping[str, Any]] = None,
        config_path: Optional[Path] = None,
    ) -> "LocalBooruConfig":
        options = dict(file_options or {})

        def option(name: str, *aliases: str, default: Any = None) -> Any:
            for key in (name, *aliases):
                if key in options and options[key] is not None:
                    return options[key]
            return default

        def resolve(name: str, *aliases: str, default: Any = None) -> Any:
            value = getattr(args, name, None)
            if value is not None:
                return value
            return option(name, *aliases, default=default)

        config_base = config_path.parent if config_path else None

        roots_option = option("roots", "directories", default=None)
        roots_sequence: list[str] = []
        if isinstance(roots_option, (list, tuple)):
            roots_sequence = [str(item) for item in roots_option if item]
        elif isinstance(roots_option, str) and roots_option:
            roots_sequence = [roots_option]

        root_key = option("root")
        config_primary: Optional[str] = str(root_key) if root_key else None

        config_additional: list[str] = []
        if roots_sequence:
            if config_primary is None:
                config_primary = roots_sequence[0]
                config_additional.extend(roots_sequence[1:])
            else:
                config_additional.extend(roots_sequence)

        extra_roots_option = option("extra_roots", "extra_root", default=None)
        if isinstance(extra_roots_option, (list, tuple)):
            config_additional.extend(str(item) for item in extra_roots_option if item)
        elif isinstance(extra_roots_option, str):
            config_additional.append(extra_roots_option)

        def resolve_config_path(value: str) -> Path:
            path = Path(value).expanduser()
            if config_base and not path.is_absolute():
                path = (config_base / path).resolve()
            else:
                path = path.resolve()
            return path

        cli_root = getattr(args, "root", None)
        root_path: Path
        if cli_root:
            root_path = Path(cli_root).expanduser().resolve()
        elif config_primary:
            root_path = resolve_config_path(config_primary)
        else:
            root_path = Path(".").resolve()

        seen_paths: set[Path] = {root_path}
        extra_paths: list[Path] = []
        for value in config_additional:
            path = resolve_config_path(value)
            if path not in seen_paths:
                extra_paths.append(path)
                seen_paths.add(path)
        for value in getattr(args, "extra_root", []) or []:
            path = Path(value).expanduser().resolve()
            if path not in seen_paths:
                extra_paths.append(path)
                seen_paths.add(path)

        db_cli = getattr(args, "db", None)
        db_option = option("db_path", "db", "database")
        if db_cli:
            db_path = Path(db_cli).expanduser().resolve()
        elif db_option:
            db_path = Path(str(db_option)).expanduser().resolve()
        elif file_options is not None:
            db_path = (_default_state_dir() / "gallery.db").resolve()
        else:
            db_path = Path("gallery.db").resolve()

        thumb_cli = getattr(args, "thumb_cache", None)
        thumb_option = option("thumb_cache", "thumbnail_cache")
        if thumb_cli:
            thumb_cache = Path(thumb_cli).expanduser().resolve()
        elif thumb_option:
            thumb_cache = Path(str(thumb_option)).expanduser().resolve()
        else:
            thumb_cache = _default_cache_dir()

        auto_tag_missing = getattr(args, "auto_tag_missing", None)
        if auto_tag_missing is None:
            auto_tag_missing = bool(option("auto_tag_missing", default=True))

        auto_tag_background = getattr(args, "auto_tag_background", None)
        if auto_tag_background is None:
            auto_tag_background = bool(option("auto_tag_background", default=True))

        webview = getattr(args, "webview", False)
        webview_option = option("webview")
        if webview_option is not None:
            webview = bool(webview_option)

        service_mode = bool(
            getattr(args, "service", False) or option("service", default=False)
        )
        watch_cli = getattr(args, "watch", False)
        watch_option = option("watch")
        watch_enabled = bool(
            watch_cli
            or (watch_option if watch_option is not None else False)
            or service_mode
        )

        no_ui = getattr(args, "no_ui", False)
        if service_mode:
            no_ui = True
            webview = False

        thumb_size_value = int(resolve("thumb_size", default=512))
        host_value = str(resolve("host", default="127.0.0.1"))
        port_value = int(resolve("port", default=8000))
        clip_device_value = str(resolve("clip_device", default="cpu"))
        clip_batch_size_value = int(resolve("clip_batch_size", default=8))
        clip_model_name_value = str(
            resolve("clip_model_name", default="ViT-B-32-quickgelu")
        )
        clip_checkpoint_value = str(resolve("clip_checkpoint", default="openai"))
        auto_tag_model_value = str(resolve("auto_tag_model", default="ConvNextV2"))
        auto_tag_general_threshold_value = float(
            resolve("auto_tag_general_threshold", default=0.35)
        )
        auto_tag_character_threshold_value = float(
            resolve("auto_tag_character_threshold", default=0.85)
        )
        auto_tag_mode_value = (
            str(resolve("auto_tag_mode", default="augment") or "augment").lower()
        )
        auto_tag_batch_size_value = max(
            1, int(resolve("auto_tag_batch_size", default=4))
        )
        log_level_value = str(resolve("log_level", default="INFO")).upper()

        return cls(
            root=root_path,
            db_path=db_path,
            thumb_cache=thumb_cache,
            thumb_size=thumb_size_value,
            host=host_value,
            port=port_value,
            watch=watch_enabled,
            rescan_interval=cls._resolve_rescan_interval(
                args, option("rescan_interval")
            ),
            enable_thumbs=not bool(
                getattr(args, "no_thumbs", False)
                or option("no_thumbs", "disable_thumbs", default=False)
            ),
            clip_device=clip_device_value,
            clip_batch_size=clip_batch_size_value,
            clip_enabled=not bool(
                getattr(args, "no_clip", False)
                or option("clip_enabled", default=True) is False
            ),
            clip_model_name=clip_model_name_value,
            clip_checkpoint=clip_checkpoint_value,
            auto_tag_missing=bool(auto_tag_missing),
            auto_tag_model=auto_tag_model_value,
            auto_tag_general_threshold=auto_tag_general_threshold_value,
            auto_tag_character_threshold=auto_tag_character_threshold_value,
            auto_tag_mode=auto_tag_mode_value,
            auto_tag_background=bool(auto_tag_background),
            auto_tag_batch_size=auto_tag_batch_size_value,
            webview=bool(webview),
            no_ui=bool(no_ui or option("no_ui", default=False)),
            log_level=log_level_value,
            extra_roots=extra_paths,
            config_file=config_path,
            service_mode=service_mode,
        )

    @property
    def clip_model_key(self) -> str:
        return f"{self.clip_model_name}:{self.clip_checkpoint}"

    @property
    def roots(self) -> list[Path]:
        return [self.root, *self.extra_roots]

    @staticmethod
    def _resolve_rescan_interval(
        args: "argparse.Namespace",
        option_value: Optional[Any],
    ) -> int:
        cli_value = getattr(args, "rescan_interval", None)
        if cli_value is not None:
            return int(cli_value)
        if option_value is not None:
            return int(option_value)
        return 600


def render_default_config_template() -> str:
    """Return an annotated TOML configuration template."""
    state_db = (_default_state_dir() / "gallery.db").expanduser()
    thumb_cache = _default_cache_dir().expanduser()
    return dedent(
        f"""\
        # LocalBooru configuration template
        # Save as ~/.localbooru.toml or point --config / LOCALBOORU_CONFIG here.

        # --- Filesystem roots --------------------------------------------------
        # Primary NovelAI directory (required).
        root = "/path/to/novelai"

        # Optional additional directories to index alongside the primary root.
        # You can also replace `root` entirely with an ordered `roots = [...]` list.
        extra_roots = []  # e.g. ["/srv/archives/novelai-b"]

        # --- Storage paths -----------------------------------------------------
        # SQLite database for image metadata. Default follows XDG_STATE_HOME.
        db_path = "{state_db}"
        # Thumbnail cache directory (XDG_CACHE_HOME/localbooru/thumbs by default).
        thumb_cache = "{thumb_cache}"
        thumb_size = 512
        no_thumbs = false

        # --- Watch/service behaviour ------------------------------------------
        watch = false
        rescan_interval = 600  # seconds; set 0 to rely solely on watchdog events
        service = false

        # --- HTTP server & UI --------------------------------------------------
        host = "127.0.0.1"
        port = 8000
        no_ui = false
        webview = false
        log_level = "INFO"

        # --- CLIP indexer ------------------------------------------------------
        clip_enabled = true
        clip_device = "cpu"  # change to "cuda" or "mps" if your torch build supports it
        clip_batch_size = 8
        clip_model_name = "ViT-B-32-quickgelu"
        clip_checkpoint = "openai"

        # --- Auto-tagging ------------------------------------------------------
        auto_tag_missing = true
        auto_tag_background = true
        auto_tag_mode = "augment"  # or "missing"
        auto_tag_model = "ConvNextV2"
        auto_tag_general_threshold = 0.35
        auto_tag_character_threshold = 0.85
        auto_tag_batch_size = 4

        # Install extras:
        #   pip install localbooru[clip,tagging,watch,ui]
        # watcher support falls back to interval scans when `watchdog` is missing.
        """
    )
