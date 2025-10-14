from __future__ import annotations

from localbooru.database import LocalBooruDatabase


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
