"""CLIP embedding management for localbooru."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, UnidentifiedImageError

from .config import LocalBooruConfig
from .database import LocalBooruDatabase

LOGGER = logging.getLogger(__name__)

_MODEL_CACHE: Dict[str, "_OpenClipModel"] = {}


def get_clip_model(config: LocalBooruConfig) -> "_OpenClipModel":
    key = config.clip_model_key
    model = _MODEL_CACHE.get(key)
    if model is None:
        model = _OpenClipModel(
            model_name=config.clip_model_name,
            checkpoint=config.clip_checkpoint,
            device=config.clip_device,
        )
        _MODEL_CACHE[key] = model
    return model


@dataclass
class ClipProgress:
    model_key: str
    total: int = 0
    completed: int = 0
    processing: int = 0
    queued: int = 0
    error_count: int = 0
    current_path: Optional[str] = None
    started_at: Optional[float] = None
    last_update: Optional[float] = None
    paused: bool = False
    errors: list[str] = field(default_factory=list)
    history: List[Tuple[float, int]] = field(default_factory=list)

    def snapshot(self, db: Optional[LocalBooruDatabase] = None) -> Dict[str, object]:
        data = asdict(self)
        if db is not None:
            total, completed, processing, errors = db.clip_progress_counts(self.model_key)
            effective_total = max(total - errors, 0)
            data.update(
                {
                    "total": total,
                    "completed": completed,
                    "processing": processing,
                    "error_count": errors,
                    "effective_total": effective_total,
                }
            )
            data["queued"] = max(effective_total - completed - processing, 0)
        data["timestamp"] = time.time()
        if self.paused:
            state = "paused"
        elif data["queued"] or data["processing"]:
            state = "running"
        else:
            state = "idle"
        data["state"] = state
        data["error_sample"] = self.errors[-5:]
        rate_per_min, eta_seconds = self._compute_rate_eta()
        data["rate_per_min"] = rate_per_min
        data["eta_seconds"] = eta_seconds
        return data

    def _record_history(self, completed: int) -> None:
        now = time.time()
        if self.history and self.history[-1][1] == completed:
            self.history[-1] = (now, completed)
        else:
            self.history.append((now, completed))
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
        remaining = max(self.queued, 0)
        if rate_per_min > 0 and remaining > 0:
            eta_seconds = (remaining / rate_per_min) * 60.0
        return rate_per_min, eta_seconds


class ClipIndexer(threading.Thread):
    def __init__(self, db: LocalBooruDatabase, config: LocalBooruConfig, progress: ClipProgress):
        super().__init__(daemon=True)
        self.db = db
        self.config = config
        self.progress = progress
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # running by default
        self._model = None

    def run(self) -> None:  # pragma: no cover - background thread
        while not self._stop_event.is_set():
            if not self._pause_event.is_set():
                self.progress.paused = True
                time.sleep(0.5)
                continue
            self.progress.paused = False
            processed_any = self._process_batch()
            if not processed_any:
                time.sleep(2.0)

    def process_until_empty(self) -> None:
        while self._process_batch():
            continue

    def _process_batch(self) -> bool:
        if not self.config.clip_enabled:
            return False
        batch = self.db.reserve_clip_batch(self.progress.model_key, self.config.clip_batch_size)
        if not batch:
            self._refresh_progress()
            self.progress.processing = 0
            if self.progress.started_at and self.progress.completed >= self.progress.total:
                self.progress.current_path = None
            return False

        self.progress.started_at = self.progress.started_at or time.time()
        images = []
        image_ids = []
        paths: list[str] = []

        for row in batch:
            rel_path = row["path"]
            abs_path = (self.config.root / rel_path) if not Path(rel_path).is_absolute() else Path(rel_path)
            try:
                img = Image.open(abs_path).convert("RGB")
            except FileNotFoundError:
                LOGGER.warning("Missing file for CLIP embedding: %s", abs_path)
                self.db.mark_clip_error(row["image_id"], "file missing")
                self._record_error(f"Missing file: {abs_path}")
                continue
            except UnidentifiedImageError:
                LOGGER.warning("Unidentified image for CLIP embedding: %s", abs_path)
                self.db.mark_clip_error(row["image_id"], "cannot identify image")
                self._record_error(f"Unidentified image: {abs_path}")
                continue
            except Exception as exc:
                LOGGER.exception("Error opening %s: %s", abs_path, exc)
                self.db.mark_clip_error(row["image_id"], str(exc))
                self._record_error(f"Open error: {abs_path}: {exc}")
                continue
            images.append(img)
            image_ids.append(row["image_id"])
            paths.append(str(abs_path))

        if not images:
            self._refresh_progress()
            return True

        self.progress.processing = len(image_ids)

        try:
            model = self._get_model()
            vectors = model.compute_image_features(images)
        except Exception as exc:
            LOGGER.exception("Failed to compute CLIP vectors: %s", exc)
            for image_id in image_ids:
                self.db.mark_clip_error(image_id, "model failure")
            self._record_error(f"Model failure: {exc}")
            self._refresh_progress()
            return True

        try:
            import numpy as np  # local import to keep dependency optional when CLIP disabled
        except ImportError as exc:
            LOGGER.error("numpy is required for CLIP embeddings: %s", exc)
            for image_id in image_ids:
                self.db.mark_clip_error(image_id, "numpy missing")
            self._record_error("numpy missing")
            self._refresh_progress()
            return True

        for image_id, vec, path in zip(image_ids, vectors, paths):
            self.progress.current_path = path
            try:
                vector_bytes = np.asarray(vec, dtype=np.float32).tobytes()
                self.db.store_clip_vector(image_id, self.progress.model_key, vector_bytes)
            except Exception as exc:
                LOGGER.exception("Failed to store CLIP vector for %s: %s", path, exc)
                self.db.mark_clip_error(image_id, "db failure")
                self._record_error(f"DB failure {path}: {exc}")

        for img in images:
            try:
                img.close()
            except Exception:  # pragma: no cover - best effort cleanup
                pass

        self._refresh_progress()
        return True

    def _get_model(self):
        if self._model is None:
            self._model = get_clip_model(self.config)
        return self._model

    def _refresh_progress(self) -> None:
        total, completed, processing, errors = self.db.clip_progress_counts(self.progress.model_key)
        effective_total = max(total - errors, 0)
        self.progress.total = total
        self.progress.completed = completed
        self.progress.processing = processing
        self.progress.error_count = errors
        self.progress.queued = max(effective_total - completed - processing, 0)
        self.progress._record_history(completed)
        self.progress.last_update = time.time()

    def pause(self) -> None:
        self._pause_event.clear()

    def resume(self) -> None:
        self._pause_event.set()

    def stop(self) -> None:
        self._stop_event.set()
        self._pause_event.set()

    def join(self, timeout: Optional[float] = None) -> None:
        super().join(timeout)

    def _record_error(self, message: str) -> None:
        self.progress.errors.append(message)
        if len(self.progress.errors) > 20:
            self.progress.errors.pop(0)


class _OpenClipModel:
    """Lazy wrapper around open_clip for computing image features."""

    def __init__(self, model_name: str, checkpoint: str, device: str):
        try:
            import open_clip
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("open_clip_torch is required for CLIP indexing") from exc

        self._device = device
        self._model, _, self._preprocess = open_clip.create_model_and_transforms(
            model_name,
            pretrained=checkpoint,
            device=device,
        )
        self._tokenizer = open_clip.get_tokenizer(model_name)
        text_projection = getattr(self._model, "text_projection", None)
        if text_projection is not None and hasattr(text_projection, "shape"):
            self._feature_dim = int(text_projection.shape[1])
        else:
            self._feature_dim = 0

    def compute_image_features(self, images: list[Image.Image]) -> np.ndarray:
        import torch
        import numpy as np

        tensors = torch.stack([self._preprocess(img) for img in images]).to(self._device)
        with torch.no_grad():
            image_features = self._model.encode_image(tensors)
            image_features /= image_features.norm(dim=-1, keepdim=True)
        result = image_features.cpu().numpy().astype(np.float32)
        return result

    def compute_text_features(self, queries: list[str]) -> np.ndarray:
        import torch
        import numpy as np

        if not queries:
            return np.zeros((1, self.feature_dim or 512), dtype=np.float32)
        tokens = self._tokenizer(queries)
        tokens = tokens.to(self._device)
        with torch.no_grad():
            text_features = self._model.encode_text(tokens)
            text_features /= text_features.norm(dim=-1, keepdim=True)
        return text_features.cpu().numpy().astype(np.float32)

    @property
    def feature_dim(self) -> int:
        if not self._feature_dim:
            self._feature_dim = 512
        return self._feature_dim
