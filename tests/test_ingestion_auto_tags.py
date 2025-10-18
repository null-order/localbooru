"""Tests for auto-tagging fallback during ingestion."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from PIL import Image

from localbooru import auto_tagging
from localbooru.config import LocalBooruConfig
from localbooru.database import LocalBooruDatabase
from localbooru.ingestion import ingest_path
from localbooru.tags import TagRecord


def _make_png(path: Path) -> None:
    Image.new("RGB", (1, 1), color=(255, 0, 0)).save(path)


def test_ingest_path_populates_missing_tags_with_wd14(monkeypatch, tmp_path) -> None:
    root = tmp_path / "gallery"
    root.mkdir()
    image_path = root / "sample.png"
    _make_png(image_path)

    generated = [
        TagRecord(
            "masterpiece",
            "masterpiece",
            "prompt",
            "normal",
            0.92,
            "wd14:masterpiece:0.920",
            "auto",
        ),
        TagRecord(
            "best_girl",
            "best_girl",
            "character",
            "normal",
            0.88,
            "wd14:best_girl:0.880",
            "auto",
        ),
    ]
    observed_args: dict[str, object] = {}

    def fake_generate(
        path: Path,
        *,
        model_name: str,
        general_threshold: float,
        character_threshold: float,
    ):
        observed_args.update(
            {
                "path": path,
                "model_name": model_name,
                "general_threshold": general_threshold,
                "character_threshold": character_threshold,
            }
        )
        return generated, {}

    monkeypatch.setattr("localbooru.ingestion.generate_wd14_tags", fake_generate)

    config = LocalBooruConfig(
        root=root,
        db_path=tmp_path / "db.sqlite",
        thumb_cache=tmp_path / "thumbs",
        clip_enabled=False,
        auto_tag_missing=True,
        auto_tag_background=False,
        auto_tag_model="wd14-convnextv2",
        auto_tag_general_threshold=0.2,
        auto_tag_character_threshold=0.7,
    )

    db = LocalBooruDatabase(config.db_path)
    try:
        ingest_path(db, config, image_path)
        rows = db.connection.execute("SELECT tag, kind, source FROM tags").fetchall()
        assert {(row["tag"], row["kind"], row["source"]) for row in rows} == {
            ("masterpiece", "prompt", "auto"),
            ("best_girl", "character", "auto"),
        }
        assert observed_args["path"] == image_path
        assert observed_args["model_name"] == "wd14-convnextv2"
        assert observed_args["general_threshold"] == 0.2
        assert observed_args["character_threshold"] == 0.7
    finally:
        db.close()


def test_ingest_path_skips_auto_tag_when_disabled(monkeypatch, tmp_path) -> None:
    root = tmp_path / "gallery2"
    root.mkdir()
    image_path = root / "no_tags.png"
    _make_png(image_path)

    def fail_generate(
        *_: object, **__: object
    ) -> list[TagRecord]:  # pragma: no cover - sanity guard
        raise AssertionError("auto-tagging should not be invoked")

    monkeypatch.setattr("localbooru.ingestion.generate_wd14_tags", fail_generate)

    config = LocalBooruConfig(
        root=root,
        db_path=tmp_path / "db2.sqlite",
        thumb_cache=tmp_path / "thumbs2",
        clip_enabled=False,
        auto_tag_missing=False,
        auto_tag_background=False,
    )

    db = LocalBooruDatabase(config.db_path)
    try:
        ingest_path(db, config, image_path)
        rows = db.connection.execute("SELECT COUNT(*) FROM tags").fetchone()
        assert rows[0] == 0
    finally:
        db.close()


def test_ingest_background_enqueues_job(monkeypatch, tmp_path) -> None:
    root = tmp_path / "gallery_bg"
    root.mkdir()
    image_path = root / "needs_background.png"
    _make_png(image_path)

    def fail_generate(
        *_: object, **__: object
    ) -> list[TagRecord]:  # pragma: no cover - safety
        raise AssertionError(
            "synchronous auto-tagging should be disabled in background mode"
        )

    monkeypatch.setattr("localbooru.ingestion.generate_wd14_tags", fail_generate)

    config = LocalBooruConfig(
        root=root,
        db_path=tmp_path / "db_background.sqlite",
        thumb_cache=tmp_path / "thumbsbg",
        clip_enabled=False,
        auto_tag_missing=True,
        auto_tag_background=True,
        auto_tag_mode="augment",
    )

    db = LocalBooruDatabase(config.db_path)
    try:
        ingest_path(db, config, image_path)
        tag_rows = db.connection.execute("SELECT COUNT(*) FROM tags").fetchone()
        assert tag_rows[0] == 0
        image_row = db.lookup_image("needs_background.png")
        assert image_row is not None
        job_row = db.connection.execute(
            "SELECT status, model FROM auto_tag_jobs WHERE image_id=?",
            (image_row["id"],),
        ).fetchone()
        assert job_row is not None
        assert job_row["status"] == "pending"
        assert job_row["model"] == "ConvNextV2"
    finally:
        db.close()


def test_existing_auto_tags_mark_job_ready(tmp_path) -> None:
    root = tmp_path / "gallery_ready"
    root.mkdir()
    image_path = root / "auto_only.png"
    _make_png(image_path)

    config = LocalBooruConfig(
        root=root,
        db_path=tmp_path / "db_ready.sqlite",
        thumb_cache=tmp_path / "thumbs_ready",
        clip_enabled=False,
        auto_tag_missing=True,
        auto_tag_background=True,
        auto_tag_mode="augment",
    )

    db = LocalBooruDatabase(config.db_path)
    try:
        ingest_path(db, config, image_path)
        image_row = db.lookup_image("auto_only.png")
        assert image_row is not None
        image_id = image_row["id"]

        db.mark_auto_tag_ready(image_id)

        ingest_path(db, config, image_path)
        status = db.get_auto_job_status(image_id)
        assert status == "ready"
    finally:
        db.close()


def test_apply_auto_tags_augments_and_skips(tmp_path) -> None:
    root = tmp_path / "gallery_merge"
    root.mkdir()
    image_path = root / "has_tags.png"
    _make_png(image_path)

    config = LocalBooruConfig(
        root=root,
        db_path=tmp_path / "db_merge.sqlite",
        thumb_cache=tmp_path / "thumbs_merge",
        clip_enabled=False,
        auto_tag_missing=False,
        auto_tag_background=False,
    )

    db = LocalBooruDatabase(config.db_path)
    try:
        embedded = [
            TagRecord(
                "sunset",
                "sunset",
                "prompt",
                "normal",
                1.0,
                "embedded:sunset",
                "embedded",
            ),
        ]
        ingest_path(db, config, image_path)
        db.upsert_image_record(
            rel_path="has_tags.png",
            name="has_tags.png",
            mtime=image_path.stat().st_mtime + 1.0,
            size=image_path.stat().st_size,
            width=1,
            height=1,
            seed=None,
            model=None,
            source=None,
            description=None,
            metadata_json=None,
            tags=embedded,
        )
        image_row = db.lookup_image("has_tags.png")
        assert image_row is not None
        image_id = image_row["id"]
        result = db.apply_auto_tags(
            image_id=image_id,
            tags=[
                TagRecord(
                    "masterpiece",
                    "masterpiece",
                    "prompt",
                    "normal",
                    0.95,
                    "wd14:masterpiece:0.950",
                    "auto",
                )
            ],
            strategy="augment",
        )
        assert result == "applied"
        rows = db.connection.execute(
            "SELECT tag, source FROM tags WHERE image_id=? ORDER BY tag",
            (image_id,),
        ).fetchall()
        assert [(row["tag"], row["source"]) for row in rows] == [
            ("masterpiece", "auto"),
            ("sunset", "embedded"),
        ]

        repeat = db.apply_auto_tags(
            image_id=image_id,
            tags=[
                TagRecord(
                    "masterpiece",
                    "masterpiece",
                    "prompt",
                    "normal",
                    0.95,
                    "wd14:masterpiece:0.950",
                    "auto",
                )
            ],
            strategy="augment",
        )
        assert repeat == "skipped"

        missing_result = db.apply_auto_tags(
            image_id=image_id,
            tags=[
                TagRecord(
                    "clouds",
                    "clouds",
                    "prompt",
                    "normal",
                    0.6,
                    "wd14:clouds:0.600",
                    "auto",
                )
            ],
            strategy="missing",
        )
        assert missing_result == "applied"
    finally:
        db.close()


def test_generate_wd14_tags_accepts_tuple(monkeypatch, tmp_path) -> None:
    from localbooru import auto_tagging as at

    test_image = tmp_path / "tuple.png"
    _make_png(test_image)

    at._WD14_LOADER = None
    at._WD14_MODEL_NAMES = ["ConvNextV2"]

    def fake_loader(
        path: str,
        *,
        model_name: str,
        general_threshold: float,
        character_threshold: float,
        fmt: Tuple[str, ...],
    ):
        assert model_name == "ConvNextV2"
        assert fmt == ("rating", "general", "character")
        return ({"explicit": 0.91}, {"masterpiece": 0.95}, {"alice": 0.87})

    monkeypatch.setattr(at, "_load_wd14", lambda: fake_loader)

    tags, scores = at.generate_wd14_tags(
        test_image,
        model_name="ConvNextV2",
        general_threshold=0.25,
        character_threshold=0.65,
    )

    lookup = {tag.tag: tag for tag in tags}
    assert set(lookup) == {"rating:explicit", "masterpiece", "alice"}
    assert lookup["rating:explicit"].kind == "rating"
    assert lookup["masterpiece"].source == "auto"
    assert lookup["alice"].kind == "character"
    assert scores == {"explicit": 0.91}
