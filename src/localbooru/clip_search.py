"""CLIP similarity search helpers for LocalBooru."""
from __future__ import annotations

import logging
from typing import Iterable, List, Sequence, Tuple

from .clip import get_clip_model
from .config import LocalBooruConfig
from .database import LocalBooruDatabase

LOGGER = logging.getLogger(__name__)


def _normalize_ids(values: Sequence[int | str]) -> List[int]:
    normalized: List[int] = []
    for value in values:
        try:
            num = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        normalized.append(num)
    return normalized


def perform_clip_search(
    db: LocalBooruDatabase,
    config: LocalBooruConfig,
    positive_text: Sequence[str] | None = None,
    negative_text: Sequence[str] | None = None,
    positive_images: Sequence[int | str] | None = None,
    negative_images: Sequence[int | str] | None = None,
    limit: int = 20,
    restrict_to_ids: Iterable[int] | None = None,
    positive_vectors: Sequence[object] | None = None,
) -> List[Tuple[int, float]]:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - optional dependency
        LOGGER.error("numpy is required for CLIP search: %s", exc)
        return []

    model = get_clip_model(config)
    positive_text = [q for q in (positive_text or []) if q]
    negative_text = [q for q in (negative_text or []) if q]
    positive_ids = _normalize_ids(positive_images or [])
    negative_ids = _normalize_ids(negative_images or [])
    positive_vector_list = list(positive_vectors or [])

    if (
        not positive_text
        and not negative_text
        and not positive_ids
        and not negative_ids
        and not positive_vector_list
    ):
        return []

    vectors_positive: List[np.ndarray] = []
    vectors_negative: List[np.ndarray] = []

    if positive_text:
        pos_features = model.compute_text_features(list(positive_text))
        if getattr(pos_features, "size", 0):  # type: ignore[attr-defined]
            vectors_positive.append(pos_features.mean(axis=0))

    if negative_text:
        neg_features = model.compute_text_features(list(negative_text))
        if getattr(neg_features, "size", 0):
            vectors_negative.append(neg_features.mean(axis=0))

    if positive_ids:
        pos_vectors: List[np.ndarray] = []
        for image_id in positive_ids:
            blob = db.fetch_clip_vector(image_id, config.clip_model_key)
            if not blob:
                LOGGER.debug("No CLIP vector for image %s", image_id)
                continue
            vec = np.frombuffer(blob, dtype=np.float32)
            if vec.size:
                pos_vectors.append(vec)
        if pos_vectors:
            vectors_positive.append(np.stack(pos_vectors, axis=0).mean(axis=0))

    if positive_vector_list:
        for vector in positive_vector_list:
            if vector is None:
                continue
            arr = np.asarray(vector, dtype=np.float32)
            if arr.size == 0:
                continue
            norm = np.linalg.norm(arr)
            if not np.isfinite(norm) or norm == 0:
                continue
            vectors_positive.append(arr / norm)

    if negative_ids:
        neg_vectors: List[np.ndarray] = []
        for image_id in negative_ids:
            blob = db.fetch_clip_vector(image_id, config.clip_model_key)
            if not blob:
                continue
            vec = np.frombuffer(blob, dtype=np.float32)
            if vec.size:
                neg_vectors.append(vec)
        if neg_vectors:
            vectors_negative.append(np.stack(neg_vectors, axis=0).mean(axis=0))

    if not vectors_positive and not vectors_negative:
        return []

    feature_dim = model.feature_dim

    combination = np.zeros(feature_dim, dtype=np.float32)
    if vectors_positive:
        combination += np.sum(np.stack(vectors_positive, axis=0), axis=0)
    if vectors_negative:
        combination -= np.sum(np.stack(vectors_negative, axis=0), axis=0)

    norm = np.linalg.norm(combination)
    if not np.isfinite(norm) or norm == 0:
        return []
    combination /= norm

    allowed_ids = set(int(i) for i in restrict_to_ids) if restrict_to_ids is not None else None

    image_ids: List[int] = []
    matrix: List[np.ndarray] = []
    for image_id, blob in db.iter_clip_vectors(config.clip_model_key):
        image_id = int(image_id)
        if allowed_ids is not None and image_id not in allowed_ids:
            continue
        vec = np.frombuffer(blob, dtype=np.float32)
        if vec.size == 0:
            continue
        matrix.append(vec)
        image_ids.append(image_id)

    if not matrix:
        return []

    matrix_np = np.stack(matrix)
    scores = matrix_np @ combination
    order = np.argsort(scores)[::-1]
    if limit and limit > 0:
        order = order[:limit]
    results = [(image_ids[i], float(scores[i])) for i in order]
    return results
