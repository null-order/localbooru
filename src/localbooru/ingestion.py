"""Image ingestion helpers for LocalBooru."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple

from .auto_tagging import AutoTaggingUnavailable, generate_wd14_tags
from .config import LocalBooruConfig
from .database import LocalBooruDatabase
from .tags import TagRecord, collect_tags, merge_tag_records, read_png_metadata

if TYPE_CHECKING:
    from .scanner import ScanProgress

LOGGER = logging.getLogger(__name__)

PNG_PATTERNS: Sequence[str] = ("*.png", "*.PNG")


@dataclass
class IngestAutoContext:
    jobs: Dict[int, Tuple[str, Optional[str]]]
    auto_tagged: set[int]

    def __init__(
        self,
        jobs: Optional[Dict[int, Tuple[str, Optional[str]]]] = None,
        auto_tagged: Optional[set[int]] = None,
    ):
        self.jobs = jobs or {}
        self.auto_tagged = auto_tagged or set()

    def job_info(self, image_id: int) -> Optional[Tuple[str, Optional[str]]]:
        return self.jobs.get(image_id)

    def job_status(self, image_id: int) -> Optional[str]:
        info = self.jobs.get(image_id)
        return info[0] if info else None

    def job_model(self, image_id: int) -> Optional[str]:
        info = self.jobs.get(image_id)
        return info[1] if info else None

    def set_job(self, image_id: int, status: str, model: Optional[str] = None) -> None:
        if model is None:
            model = self.job_model(image_id)
        self.jobs[image_id] = (status, model)

    def has_auto_tags(self, image_id: int) -> bool:
        return image_id in self.auto_tagged

    def add_auto_tags(self, image_id: int) -> None:
        self.auto_tagged.add(image_id)

    def remove_auto_tags(self, image_id: int) -> None:
        self.auto_tagged.discard(image_id)


def ingest_path(
    db: LocalBooruDatabase,
    config: LocalBooruConfig,
    path: Path,
    *,
    context: Optional[IngestAutoContext] = None,
) -> Optional[int]:
    root = config.root
    if not path.is_file():
        return None
    try:
        rel_path = path.relative_to(root).as_posix()
    except ValueError:
        # Fallback for extra roots - compute relative with respect to path drive
        rel_path = path.as_posix()
    stat = path.stat()
    existing = db.lookup_image(rel_path)
    unchanged = False
    if existing is not None:
        if (
            abs(existing["mtime"] - stat.st_mtime) < 1e-6
            and existing["size"] == stat.st_size
        ):
            unchanged = True

    if unchanged:
        image_id = existing["id"]
        changed = False
        tags = []
        description_text = (
            existing["description"] if "description" in existing.keys() else None
        )
        comment_meta = {}
        chunks = {}
    else:
        chunks = read_png_metadata(path)
        tags, description_text, comment_meta = collect_tags(chunks)

    auto_enabled = config.auto_tag_missing
    auto_mode = (config.auto_tag_mode or "missing").lower()
    auto_tags: List[TagRecord] = []
    manual_tags_present = bool(tags)

    auto_rating_scores: Optional[Dict[str, float]] = None
    if auto_enabled and not config.auto_tag_background:
        if unchanged:
            missing_auto_rating = not db.has_rating_tag(image_id)
        else:
            missing_auto_rating = True
        should_generate = (
            auto_mode == "augment"
            or not manual_tags_present
            or missing_auto_rating
        )
        if should_generate:
            try:
                auto_tags, auto_rating_scores = generate_wd14_tags(
                    path,
                    model_name=config.auto_tag_model,
                    general_threshold=config.auto_tag_general_threshold,
                    character_threshold=config.auto_tag_character_threshold,
                )
                if auto_tags:
                    LOGGER.info(
                        "WD14 generated %d tags for %s", len(auto_tags), path.name
                    )
            except AutoTaggingUnavailable as exc:
                LOGGER.warning("Auto-tagging unavailable: %s", exc)
            except (
                Exception
            ) as exc:  # pragma: no cover - defensive around external model
                LOGGER.exception("WD14 tagging failed for %s: %s", path, exc)

    if not unchanged:
        if auto_tags:
            tags = merge_tag_records(tags, auto_tags)
        width = _safe_int(chunks.get("Width") or comment_meta.get("width"))
        height = _safe_int(chunks.get("Height") or comment_meta.get("height"))
        seed = comment_meta.get("seed")
        model = (
            comment_meta.get("Source")
            or comment_meta.get("source")
            or chunks.get("Source")
        )
        source = (
            chunks.get("Source")
            or comment_meta.get("Source")
            or comment_meta.get("source")
        )
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
    else:
        image_id = existing["id"]
        changed = False
    if auto_rating_scores:
        db.update_rating_from_scores(image_id, auto_rating_scores)
    if auto_enabled:
        inserted_auto_tags = any(tag.source == "auto" for tag in tags)
        if context is not None:
            job_status = context.job_status(image_id)
            existing_auto_tags = context.has_auto_tags(image_id)
        else:
            job_status = db.get_auto_job_status(image_id)
            existing_auto_tags = db.has_auto_tags(image_id)
        missing_auto_rating = not db.has_rating_tag(image_id)

        if config.auto_tag_background:
            if job_status in {"pending", "processing"} and existing_auto_tags:
                db.mark_auto_tag_ready(image_id)
                if context is not None:
                    context.set_job(image_id, "ready")
                job_status = "ready"
            elif job_status == "error" and existing_auto_tags:
                db.mark_auto_tag_ready(image_id)
                if context is not None:
                    context.set_job(image_id, "ready")
                job_status = "ready"
            else:
                needs_job = False
                if auto_mode == "augment":
                    if changed:
                        needs_job = True
                    elif missing_auto_rating:
                        needs_job = True
                    elif (
                        job_status in {None, "pending", "processing", "error"}
                        and not existing_auto_tags
                    ):
                        needs_job = True
                else:
                    if not manual_tags_present:
                        if changed:
                            needs_job = True
                        elif (
                            job_status in {None, "pending", "processing", "error"}
                            and not existing_auto_tags
                        ):
                            needs_job = True
                    elif missing_auto_rating:
                        needs_job = True

                if needs_job:
                    force_reset = (
                        changed
                        or job_status == "error"
                        or (
                            job_status in {"pending", "processing"}
                            and not existing_auto_tags
                        )
                        or missing_auto_rating
                    )
                    db.ensure_auto_tag_job(
                        image_id,
                        config.auto_tag_model,
                        force_reset=force_reset,
                    )
                    if context is not None:
                        context.set_job(image_id, "pending", config.auto_tag_model)
                    job_status = "pending"
                elif (
                    existing_auto_tags
                    and job_status
                    and job_status not in {"ready", "skipped"}
                    and not missing_auto_rating
                ):
                    db.mark_auto_tag_ready(image_id)
                    if context is not None:
                        context.set_job(image_id, "ready")
                    job_status = "ready"
        elif (
            existing_auto_tags
            and job_status
            and job_status not in {"ready", "skipped"}
            and not missing_auto_rating
        ):
            db.mark_auto_tag_ready(image_id)
            if context is not None:
                context.set_job(image_id, "ready")
            job_status = "ready"

        if context is not None and changed:
            if inserted_auto_tags:
                context.add_auto_tags(image_id)
            else:
                context.remove_auto_tags(image_id)
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


def scan_pngs(
    db: LocalBooruDatabase,
    config: LocalBooruConfig,
    *,
    progress: Optional["ScanProgress"] = None,
) -> None:
    roots = list(config.roots)
    all_candidates: list[Path] = []
    seen_candidates: set[str] = set()
    observed_paths: set[str] = set()
    context: Optional[IngestAutoContext] = None
    if config.auto_tag_missing:
        jobs = db.load_auto_tag_jobs()
        tagged_ids = db.load_auto_tagged_ids()
        context = IngestAutoContext(jobs=jobs, auto_tagged=tagged_ids)
    for root in roots:
        for pattern in PNG_PATTERNS:
            for path in Path(root).rglob(pattern):
                key = path.as_posix()
                if key in seen_candidates:
                    continue
                seen_candidates.add(key)
                all_candidates.append(path)

    if progress is not None:
        progress.begin(len(all_candidates))

    for path in all_candidates:
        if progress is not None:
            progress.step_start(path.as_posix())
        encountered_error = False
        try:
            ingest_path(db, config, path, context=context)
            try:
                rel_path = path.relative_to(config.root).as_posix()
            except ValueError:
                rel_path = path.as_posix()
            observed_paths.add(rel_path)
        except Exception as exc:  # pragma: no cover - defensive
            encountered_error = True
            LOGGER.exception("Failed to ingest %s: %s", path, exc)
        finally:
            if progress is not None:
                progress.step_finish(error=encountered_error)
    if progress is not None:
        progress.finish()
    if observed_paths:
        deleted = db.delete_missing_images(observed_paths)
        if deleted:
            LOGGER.info("Pruned %d missing images", deleted)
