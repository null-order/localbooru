"""CLIP similarity search helpers for LocalBooru."""
from __future__ import annotations

import logging
from typing import Iterable, List, Sequence, Tuple

from .clip import get_clip_model
from .config import LocalBooruConfig
from .database import LocalBooruDatabase

LOGGER = logging.getLogger(__name__)


def perform_clip_search(
    db: LocalBooruDatabase,
    config: LocalBooruConfig,
    positive: Sequence[str],
    negative: Sequence[str],
    limit: int = 20,
    restrict_to_ids: Iterable[int] | None = None,
) -> List[Tuple[int, float]]:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - optional dependency
        LOGGER.error("numpy is required for CLIP search: %s", exc)
        return []

    model = get_clip_model(config)
    positive = [q for q in positive if q]
    negative = [q for q in negative if q]

    if not positive and not negative:
        return []

    pos_features = model.compute_text_features(list(positive)) if positive else None
    neg_features = model.compute_text_features(list(negative)) if negative else None

    if pos_features is None and neg_features is None:
        return []

    vector = None
    if pos_features is not None:
        vector = pos_features.mean(axis=0)
    if neg_features is not None:
        neg_vector = neg_features.mean(axis=0)
        vector = (-neg_vector) if vector is None else vector - neg_vector

    if vector is None:
        return []

    vector = vector.astype(np.float32)
    norm = np.linalg.norm(vector)
    if norm == 0:
        return []
    vector /= norm

    allowed_ids = set(int(i) for i in restrict_to_ids) if restrict_to_ids is not None else None

    image_ids: List[int] = []
    matrix: List[np.ndarray] = []
    for row in db.iter_clip_vectors(config.clip_model_key):
        image_id = int(row["image_id"])
        if allowed_ids is not None and image_id not in allowed_ids:
            continue
        blob = row["vector"]
        vec = np.frombuffer(blob, dtype=np.float32)
        if vec.size == 0:
            continue
        matrix.append(vec)
        image_ids.append(image_id)

    if not matrix:
        return []

    matrix_np = np.stack(matrix)
    scores = matrix_np @ vector
    top_indices = np.argsort(scores)[::-1][:limit]
    results = [(image_ids[i], float(scores[i])) for i in top_indices]
    return results
