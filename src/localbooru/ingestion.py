"""Image ingestion helpers for LocalBooru."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Sequence

from .config import LocalBooruConfig
from .database import LocalBooruDatabase
from .tags import TagRecord, collect_tags, read_png_metadata

LOGGER = logging.getLogger(__name__)

PNG_PATTERNS: Sequence[str] = ("*.png", "*.PNG")


def ingest_path(db: LocalBooruDatabase, config: LocalBooruConfig, path: Path) -> Optional[int]:
    root = config.root
    if not path.is_file():
        return None
    try:
        rel_path = path.relative_to(root).as_posix()
    except ValueError:
        # Fallback for extra roots - compute relative with respect to path drive
        rel_path = path.as_posix()
    stat = path.stat()
    chunks = read_png_metadata(path)
    tags, description_text, comment_meta = collect_tags(chunks)
    width = _safe_int(chunks.get("Width") or comment_meta.get("width"))
    height = _safe_int(chunks.get("Height") or comment_meta.get("height"))
    seed = comment_meta.get("seed")
    model = comment_meta.get("Source") or comment_meta.get("source") or chunks.get("Source")
    source = chunks.get("Source") or comment_meta.get("Source") or comment_meta.get("source")
    metadata_blob = json.dumps(comment_meta) if comment_meta else None
    image_id, changed = db.upsert_image_record(
        rel_path=rel_path,
        name=path.name,
        mtime=stat.st_mtime,
        size=stat.st_size,
        width=width,
        height=height,
        seed=str(seed) if seed is not None else None,
        model=model,
        source=source,
        description=description_text,
        metadata_json=metadata_blob,
        tags=tags,
    )
    if config.clip_enabled:
        db.ensure_clip_entry(image_id, config.clip_model_key, force_reset=changed)
    return image_id


def _safe_int(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def scan_pngs(db: LocalBooruDatabase, config: LocalBooruConfig) -> None:
    roots = [config.root, *config.extra_roots]
    for root in roots:
        for pattern in PNG_PATTERNS:
            for path in Path(root).rglob(pattern):
                try:
                    ingest_path(db, config, path)
                except Exception as exc:  # pragma: no cover - defensive
                    LOGGER.exception("Failed to ingest %s: %s", path, exc)
