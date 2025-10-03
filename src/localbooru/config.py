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
    webview: bool = True
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
            cache_root = Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache")).expanduser()
            thumb_cache = (cache_root / "localbooru" / "thumbs").resolve()
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
            webview=not args.no_webview,
            no_ui=args.no_ui,
            log_level=args.log_level,
            extra_roots=[Path(p).resolve() for p in args.extra_root or []],
        )

    @property
    def clip_model_key(self) -> str:
        return f"{self.clip_model_name}:{self.clip_checkpoint}"
