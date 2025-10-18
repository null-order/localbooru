"""Automatic tagging helpers backed by the WD14 family of models."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image

from .config import LocalBooruConfig
from .database import LocalBooruDatabase
from .tags import TagRecord, normalize_tag

LOGGER = logging.getLogger(__name__)


class AutoTaggingUnavailable(RuntimeError):
    """Raised when optional auto-tagging dependencies are missing."""


_WD14_LOADER: Optional[Callable[..., object]] = None
_WD14_MODEL_NAMES: Optional[List[str]] = None


@dataclass
class AutoTagProgress:
    total: int = 0
    completed: int = 0
    processing: int = 0
    queued: int = 0
    error_count: int = 0
    current_path: Optional[str] = None
    last_update: Optional[float] = None
    errors: list[str] = field(default_factory=list)
    history: List[Tuple[float, int]] = field(default_factory=list)
    paused: bool = False

    def snapshot(self, db: Optional[LocalBooruDatabase] = None) -> dict[str, object]:
        data = {
            "total": self.total,
            "completed": self.completed,
            "processing": self.processing,
            "queued": self.queued,
            "error_count": self.error_count,
            "current_path": self.current_path,
            "last_update": self.last_update,
            "errors": self.errors[-5:],
            "paused": self.paused,
        }
        if db is not None:
            total, completed, processing, errors = db.auto_tag_progress_counts()
            queued = max(total - completed - processing - errors, 0)
            data.update(
                {
                    "total": total,
                    "completed": completed,
                    "processing": processing,
                    "error_count": errors,
                    "queued": queued,
                }
            )
        data["timestamp"] = time.time()
        rate_per_min, eta_seconds = self._compute_rate_eta()
        data["rate_per_min"] = rate_per_min
        data["eta_seconds"] = eta_seconds
        if self.paused:
            state = "paused"
        elif data["processing"] or data.get("queued", 0):
            state = "running"
        else:
            state = "idle"
        data["state"] = state
        return data

    def refresh_from_db(self, db: LocalBooruDatabase) -> None:
        total, completed, processing, errors = db.auto_tag_progress_counts()
        queued = max(total - completed - processing - errors, 0)
        self.total = total
        self.completed = completed
        self.processing = processing
        self.error_count = errors
        self.queued = queued
        self.last_update = time.time()
        self._record_history(completed)

    def _record_history(self, completed: int) -> None:
        now = time.time()
        if self.history and self.history[-1][1] == completed:
            self.history[-1] = (now, completed)
        else:
            self.history.append((now, completed))
        # keep last 60 entries (~minutes worth)
        if len(self.history) > 60:
            self.history = self.history[-60:]

    def _compute_rate_eta(self) -> Tuple[float, Optional[float]]:
        if not self.history:
            return 0.0, None
        latest_time, latest_completed = self.history[-1]
        rate_per_min = 0.0
        eta_seconds = None
        for past_time, past_completed in reversed(self.history[:-1]):
            delta_count = latest_completed - past_completed
            delta_time = latest_time - past_time
            if delta_count > 0 and delta_time >= 1.0:
                rate_per_min = (delta_count / delta_time) * 60.0
                break
        remaining = max(self.queued + self.processing, 0)
        if rate_per_min > 0 and remaining > 0:
            eta_seconds = (remaining / rate_per_min) * 60.0
        return rate_per_min, eta_seconds


class AutoTagIndexer(threading.Thread):
    def __init__(
        self,
        db: LocalBooruDatabase,
        config: LocalBooruConfig,
        progress: AutoTagProgress,
    ) -> None:
        super().__init__(daemon=True)
        self.db = db
        self.config = config
        self.progress = progress
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self.progress.paused = False

    def run(self) -> None:  # pragma: no cover - background worker
        while not self._stop_event.is_set():
            if not self._pause_event.is_set():
                self.progress.paused = True
                time.sleep(0.5)
                continue
            self.progress.paused = False
            processed = self._process_batch()
            if not processed:
                time.sleep(2.0)

    def process_until_empty(self) -> None:
        while self._process_batch():
            continue

    def stop(self) -> None:
        self._stop_event.set()
        self._pause_event.set()

    def join(self, timeout: Optional[float] = None) -> None:
        super().join(timeout)

    def pause(self) -> None:
        self._pause_event.clear()
        self.progress.paused = True

    def resume(self) -> None:
        self._pause_event.set()
        self.progress.paused = False

    def is_paused(self) -> bool:
        return not self._pause_event.is_set()

    def _record_error(self, message: str) -> None:
        self.progress.errors.append(message)
        if len(self.progress.errors) > 20:
            self.progress.errors.pop(0)

    def _process_batch(self) -> bool:
        if not self._pause_event.is_set():
            return False
        batch = self.db.reserve_auto_tag_batch(self.config.auto_tag_batch_size)
        if not batch:
            self.progress.processing = 0
            self.progress.current_path = None
            self.progress.refresh_from_db(self.db)
            return False

        self.progress.processing = len(batch)
        self.progress.current_path = None

        for row in batch:
            image_id = row["image_id"]
            rel_path = row["path"]
            path = Path(rel_path)
            if not path.is_absolute():
                path = self.config.root / rel_path
            self.progress.current_path = str(path)
            try:
                tags, rating_scores = generate_wd14_tags(
                    path,
                    model_name=self.config.auto_tag_model,
                    general_threshold=self.config.auto_tag_general_threshold,
                    character_threshold=self.config.auto_tag_character_threshold,
                )
            except AutoTaggingUnavailable as exc:
                LOGGER.error("Auto-tagging unavailable: %s", exc)
                self.db.mark_auto_tag_error(image_id, str(exc))
                self._record_error(str(exc))
                continue
            except (Image.UnidentifiedImageError, OSError) as exc:
                # Handle corrupted/invalid image files more gracefully
                if "cannot identify image file" in str(exc) or "truncated" in str(exc):
                    LOGGER.debug(
                        "Skipping corrupted/invalid image %s: %s", path.name, exc
                    )
                    self.db.mark_auto_tag_error(image_id, f"Invalid image: {exc}")
                    self._record_error(f"{path.name}: Invalid image file")
                else:
                    LOGGER.warning("Image processing error for %s: %s", path.name, exc)
                    self.db.mark_auto_tag_error(image_id, str(exc))
                    self._record_error(f"{path.name}: {exc}")
                continue
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.error("Failed to auto-tag %s: %s", path.name, exc)
                self.db.mark_auto_tag_error(image_id, str(exc))
                self._record_error(f"{path.name}: {exc}")
                continue

            try:
                status = self.db.apply_auto_tags(
                    image_id,
                    tags,
                    strategy=self.config.auto_tag_mode,
                    rating_scores=rating_scores,
                )
            except sqlite3.OperationalError as exc:
                if "locked" in str(exc).lower():
                    LOGGER.warning(
                        "SQLite busy while applying auto-tags for %s; marking job as error",
                        path,
                    )
                    self.db.mark_auto_tag_error(image_id, "database is locked")
                    self._record_error(f"{path}: database is locked")
                    continue
                raise
            if status == "skipped":
                self.db.mark_auto_tag_skipped(image_id)
            else:
                self.db.mark_auto_tag_ready(image_id)

        self.progress.processing = 0
        self.progress.current_path = None
        self.progress.refresh_from_db(self.db)
        return True


def _load_wd14() -> Callable[..., object]:
    global _WD14_LOADER
    if _WD14_LOADER is not None:  # pragma: no cover - simple cache
        return _WD14_LOADER
    try:  # pragma: no cover - exercised indirectly when dependency present
        module = import_module("imgutils.tagging")
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency missing
        raise AutoTaggingUnavailable(
            "dghs-imgutils is required for --auto-tag-missing; install with "
            "`pip install 'dghs-imgutils'` (or 'dghs-imgutils[gpu]' when using CUDA/ROCm)."
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive around dynamic loader
        raise AutoTaggingUnavailable(f"Unable to load imgutils.tagging: {exc}") from exc
    try:
        loader = getattr(module, "get_wd14_tags")
    except AttributeError as exc:  # pragma: no cover - API drift safeguard
        raise AutoTaggingUnavailable(
            "imgutils.tagging.get_wd14_tags is unavailable"
        ) from exc
    _WD14_LOADER = loader
    global _WD14_MODEL_NAMES
    if _WD14_MODEL_NAMES is None:
        try:
            wd14_module = import_module("imgutils.tagging.wd14")
            model_dict = getattr(wd14_module, "MODEL_NAMES", {})
            if isinstance(model_dict, dict):
                _WD14_MODEL_NAMES = list(model_dict.keys())
        except Exception:  # pragma: no cover - best effort cache
            _WD14_MODEL_NAMES = []
    return loader


def _normalize_model_key(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _resolve_wd14_model_name(requested: str) -> str:
    if _WD14_MODEL_NAMES is None:
        _load_wd14()
    available = _WD14_MODEL_NAMES or []
    if not available:
        available = ["ConvNextV2"]
    preferred = "ConvNextV2" if "ConvNextV2" in available else available[0]

    if not requested:
        return preferred

    aliases = {}
    for name in available:
        aliases[_normalize_model_key(name)] = name
        aliases[name.lower()] = name

    # Common SmilingWolf naming variants
    aliases.update(
        {
            "wd14convnextv2": "ConvNextV2",
            "convnextv2": "ConvNextV2",
            "convnext": "ConvNext",
            "wd14convnext": "ConvNext",
            "wd14vit": "ViT",
            "vit": "ViT",
            "vitlarge": "ViT_Large",
            "wd14vitlarge": "ViT_Large",
            "moat": "MOAT",
            "wd14moat": "MOAT",
            "swinv2": "SwinV2",
            "wd14swinv2": "SwinV2",
            "swinv2v3": "SwinV2_v3",
            "convnextv3": "ConvNext_v3",
        }
    )

    normalized = _normalize_model_key(requested)
    candidate = aliases.get(normalized)
    if candidate is None:
        candidate = aliases.get(requested.lower())

    if candidate:
        return candidate

    if requested in available:
        return requested

    suggestions = ", ".join(sorted(available))
    raise AutoTaggingUnavailable(
        f"WD14 model '{requested}' is not available. Choose one of: {suggestions}"
    )


def generate_wd14_tags(
    image_path: Path,
    *,
    model_name: str,
    general_threshold: float,
    character_threshold: float,
) -> Tuple[List[TagRecord], Dict[str, float]]:
    """Return WD14-generated tags and rating scores for ``image_path``."""
    loader = _load_wd14()
    model_name = _resolve_wd14_model_name(model_name)
    LOGGER.debug(
        "Generating WD14 tags",
        extra={
            "path": str(image_path),
            "model": model_name,
            "general_threshold": general_threshold,
            "character_threshold": character_threshold,
        },
    )

    try:
        wd14_tags = loader(  # type: ignore[call-arg, misc]
            str(image_path),
            model_name=model_name,
            general_threshold=general_threshold,
            character_threshold=character_threshold,
            fmt=("rating", "general", "character"),
        )
    except KeyError as exc:
        available = ", ".join(sorted(_WD14_MODEL_NAMES or []))
        raise AutoTaggingUnavailable(
            f"WD14 model '{model_name}' is not available: {exc}. Installed models: {available or 'unknown'}"
        ) from exc

    def _coerce_tag_map(payload: object) -> Dict[str, float]:
        if isinstance(payload, dict):
            return {
                str(k): float(v)
                for k, v in payload.items()
                if isinstance(v, (int, float))
            }
        return {}

    rating_map: Dict[str, float] = {}
    general_map: Dict[str, float] = {}
    character_map: Dict[str, float] = {}

    if hasattr(wd14_tags, "rating"):
        rating_map = _coerce_tag_map(getattr(wd14_tags, "rating"))
    if hasattr(wd14_tags, "general") and hasattr(wd14_tags, "character"):
        general_map = _coerce_tag_map(getattr(wd14_tags, "general"))
        character_map = _coerce_tag_map(getattr(wd14_tags, "character"))
    elif isinstance(wd14_tags, (tuple, list)):
        if wd14_tags:
            rating_map = _coerce_tag_map(wd14_tags[0])
        if len(wd14_tags) > 1:
            general_map = _coerce_tag_map(wd14_tags[1])
        if len(wd14_tags) > 2:
            character_map = _coerce_tag_map(wd14_tags[2])
    elif isinstance(wd14_tags, dict):
        rating_map = _coerce_tag_map(wd14_tags.get("rating"))
        general_map = _coerce_tag_map(wd14_tags.get("general"))
        character_map = _coerce_tag_map(wd14_tags.get("character"))
    else:  # pragma: no cover - unexpected library change
        raise AutoTaggingUnavailable(
            f"Unsupported WD14 response type: {type(wd14_tags)!r}"
        )

    records: List[TagRecord] = []

    if rating_map:
        normalized_scores = {
            str(key).lower(): float(value)
            for key, value in rating_map.items()
            if isinstance(value, (int, float))
        }
        rating_map = normalized_scores
        best_label, best_score = max(
            normalized_scores.items(), key=lambda item: item[1], default=(None, None)
        )
        if best_label and isinstance(best_score, (int, float)):
            rating_label = str(best_label).lower()
            norm = rating_label
            if norm:
                records.append(
                    TagRecord(
                        tag=f"rating:{rating_label}",
                        norm=norm,
                        kind="rating",
                        emphasis="normal",
                        weight=float(best_score),
                        raw=json.dumps(
                            {
                                "source": "wd14",
                                "scores": normalized_scores,
                            },
                            sort_keys=True,
                        ),
                        source="auto",
                    )
                )

    general_tags = sorted(general_map.items(), key=lambda item: (-item[1], item[0]))
    for tag, score in general_tags:
        norm = normalize_tag(tag)
        if not norm:
            continue
        records.append(
            TagRecord(
                tag=tag,
                norm=norm,
                kind="prompt",
                emphasis="normal",
                weight=float(score),
                raw=f"wd14:{tag}:{score:.3f}",
                source="auto",
            )
        )

    character_tags = sorted(character_map.items(), key=lambda item: (-item[1], item[0]))
    for tag, score in character_tags:
        norm = normalize_tag(tag)
        if not norm:
            continue
        records.append(
            TagRecord(
                tag=tag,
                norm=norm,
                kind="character",
                emphasis="normal",
                weight=float(score),
                raw=f"wd14:{tag}:{score:.3f}",
                source="auto",
            )
        )

    return records, rating_map


__all__ = [
    "generate_wd14_tags",
    "AutoTaggingUnavailable",
    "AutoTagProgress",
    "AutoTagIndexer",
]
