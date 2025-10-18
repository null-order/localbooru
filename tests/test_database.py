from __future__ import annotations

import sqlite3

from localbooru.database import LocalBooruDatabase
from localbooru.tags import TagRecord


def test_delete_missing_images_handles_large_batches(tmp_path):
    db_path = tmp_path / "gallery.db"
    db = LocalBooruDatabase(db_path)
    total = 1205  # exceeds SQLite's default variable limit (999)
    keep_paths = set()
    for index in range(total):
        rel_path = f"img_{index}.png"
        db.upsert_image_record(
            rel_path=rel_path,
            name=f"Image {index}",
            mtime=float(index),
            size=index + 100,
            width=None,
            height=None,
            seed=None,
            model=None,
            source=None,
            description=None,
            metadata_json=None,
            tags=[],
        )
        if index % 2 == 0:
            keep_paths.add(rel_path)

    deleted = db.delete_missing_images(keep_paths)
    assert deleted == total - len(keep_paths)

    rows = db.connection.execute("SELECT path FROM images").fetchall()
    remaining = {row["path"] for row in rows}
    assert remaining == keep_paths
    db.close()


def test_delete_missing_images_clears_tags_and_index(tmp_path):
    db_path = tmp_path / "gallery.db"
    db = LocalBooruDatabase(db_path)

    tag = TagRecord(
        tag="masterpiece",
        norm="masterpiece",
        kind="prompt",
        emphasis="normal",
        weight=1.0,
        raw="masterpiece",
        source="embedded",
    )

    db.upsert_image_record(
        rel_path="img.png",
        name="img.png",
        mtime=0.0,
        size=1,
        width=None,
        height=None,
        seed=None,
        model=None,
        source=None,
        description=None,
        metadata_json=None,
        tags=[tag],
    )

    assert (
        db.connection.execute("SELECT COUNT(*) FROM tags").fetchone()[0] == 1
    )
    assert (
        db.connection.execute("SELECT COUNT(*) FROM tag_index").fetchone()[0]
        == 1
    )

    deleted = db.delete_missing_images([])
    assert deleted == 1
    assert (
        db.connection.execute("SELECT COUNT(*) FROM images").fetchone()[0] == 0
    )
    assert (
        db.connection.execute("SELECT COUNT(*) FROM tags").fetchone()[0] == 0
    )
    assert (
        db.connection.execute("SELECT COUNT(*) FROM tag_index").fetchone()[0]
        == 0
    )
    db.close()


def test_auto_tag_progress_counts_empty(tmp_path):
    db_path = tmp_path / "gallery.db"
    db = LocalBooruDatabase(db_path)
    assert db.auto_tag_progress_counts() == (0, 0, 0, 0)
    db.close()


def test_clip_progress_counts_safe_defaults(tmp_path):
    db_path = tmp_path / "gallery.db"
    db = LocalBooruDatabase(db_path)
    assert db.clip_progress_counts("") == (0, 0, 0, 0)
    assert db.clip_progress_counts("ViT-B-32-quickgelu:openai") == (0, 0, 0, 0)
    db.close()


def test_apply_auto_tags_retries_when_locked(monkeypatch, tmp_path):
    db_path = tmp_path / "retry.db"
    db = LocalBooruDatabase(db_path)
    image_id, _ = db.upsert_image_record(
        rel_path="img.png",
        name="img.png",
        mtime=0.0,
        size=1,
        width=1,
        height=1,
        seed=None,
        model=None,
        source=None,
        description=None,
        metadata_json=None,
        tags=[],
    )

    original = LocalBooruDatabase._apply_auto_tags_internal
    call_state = {"attempts": 0}

    def flaky(self, conn, img_id, tag_records, strategy):
        if call_state["attempts"] < 2:
            call_state["attempts"] += 1
            raise sqlite3.OperationalError("database is locked")
        return original(self, conn, img_id, tag_records, strategy)

    monkeypatch.setattr(LocalBooruDatabase, "_apply_auto_tags_internal", flaky)

    tag = TagRecord(
        tag="masterpiece",
        norm="masterpiece",
        kind="prompt",
        emphasis="normal",
        weight=0.9,
        raw="auto:masterpiece",
        source="auto",
    )

    try:
        result = db.apply_auto_tags(image_id, [tag], strategy="augment")
        assert result == "applied"
        assert call_state["attempts"] == 2
    finally:
        db.close()


def test_store_clip_vector_retries_when_locked(monkeypatch, tmp_path):
    db_path = tmp_path / "clip_retry.db"
    db = LocalBooruDatabase(db_path)
    try:
        image_id, _ = db.upsert_image_record(
            rel_path="img2.png",
            name="img2.png",
            mtime=0.0,
            size=1,
            width=1,
            height=1,
            seed=None,
            model=None,
            source=None,
            description=None,
            metadata_json=None,
            tags=[],
        )
        db.ensure_clip_entry(image_id, model="test", force_reset=True)

        call_state = {"attempts": 0}

        original_new_connection = LocalBooruDatabase.new_connection

        class FlakyConnection:
            def __init__(self, inner_conn):
                self._inner = inner_conn

            def execute(self, sql, params=()):
                if (
                    "UPDATE clip_embeddings SET status='ready'" in sql
                    and call_state["attempts"] < 2
                ):
                    call_state["attempts"] += 1
                    raise sqlite3.OperationalError("database is locked")
                return self._inner.execute(sql, params)

            def executemany(self, sql, seq):
                return self._inner.executemany(sql, seq)

            def __getattr__(self, name):
                return getattr(self._inner, name)

            def __enter__(self):
                self._inner.__enter__()
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                return self._inner.__exit__(exc_type, exc_val, exc_tb)

        def flaky_new_connection(self):
            return FlakyConnection(original_new_connection(self))

        monkeypatch.setattr(
            LocalBooruDatabase, "new_connection", flaky_new_connection, raising=False
        )

        db.store_clip_vector(image_id, "test", b"\x00\x01")
        assert call_state["attempts"] == 2

        row = db.fetch_clip_vector(image_id, "test")
        assert row == b"\x00\x01"
    finally:
        db.close()
