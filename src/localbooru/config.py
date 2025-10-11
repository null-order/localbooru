"""Configuration helpers for localbooru."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


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
    rating_missing: bool = True
    rating_model: str = "mobilenetv3_large_100_v0_ls0.2"
    rating_background: bool = True
    rating_batch_size: int = 4
    webview: bool = False
    no_ui: bool = False
    log_level: str = "INFO"
    extra_roots: list[Path] = field(default_factory=list)

    @classmethod
    def from_args(cls, args: "argparse.Namespace") -> "LocalBooruConfig":
        root = Path(args.root).resolve()
        db_path = Path(args.db).resolve()

        if args.thumb_cache:
            thumb_cache = Path(args.thumb_cache).expanduser().resolve()
        else:
            cache_root = Path(
                os.getenv("XDG_CACHE_HOME", Path.home() / ".cache")
            ).expanduser()
            thumb_cache = (cache_root / "localbooru" / "thumbs").resolve()

        auto_tag_missing = args.auto_tag_missing
        if auto_tag_missing is None:
            auto_tag_missing = True

        auto_tag_background = args.auto_tag_background
        if auto_tag_background is None:
            auto_tag_background = True

        rating_missing = args.rate_missing
        if rating_missing is None:
            rating_missing = True

        rating_background = args.rate_background
        if rating_background is None:
            rating_background = True

        return cls(
            root=root,
            db_path=db_path,
            thumb_cache=thumb_cache,
            thumb_size=args.thumb_size,
            host=args.host,
            port=args.port,
            watch=args.watch,
            rescan_interval=args.rescan_interval,
            enable_thumbs=not args.no_thumbs,
            clip_device=args.clip_device,
            clip_batch_size=args.clip_batch_size,
            clip_enabled=not args.no_clip,
            clip_model_name=args.clip_model_name,
            clip_checkpoint=args.clip_checkpoint,
            auto_tag_missing=auto_tag_missing,
            auto_tag_model=args.auto_tag_model,
            auto_tag_general_threshold=args.auto_tag_general_threshold,
            auto_tag_character_threshold=args.auto_tag_character_threshold,
            auto_tag_mode=str(args.auto_tag_mode).lower(),
            auto_tag_background=auto_tag_background,
            auto_tag_batch_size=max(1, int(args.auto_tag_batch_size)),
            rating_missing=rating_missing,
            rating_model=args.rate_model,
            rating_background=rating_background,
            rating_batch_size=max(1, int(args.rate_batch_size)),
            webview=bool(args.webview),
            no_ui=args.no_ui,
            log_level=args.log_level,
            extra_roots=[Path(p).resolve() for p in args.extra_root or []],
        )

    @property
    def clip_model_key(self) -> str:
        return f"{self.clip_model_name}:{self.clip_checkpoint}"
