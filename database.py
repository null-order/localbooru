"""SQLite persistence layer for localbooru."""
from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

from .tags import TagRecord

SCHEMA_STATEMENTS = [
    "PRAGMA journal_mode=WAL;",
    "PRAGMA synchronous=NORMAL;",
    "PRAGMA foreign_keys = ON;",
    "CREATE TABLE IF NOT EXISTS images (\n        id INTEGER PRIMARY KEY,\n        path TEXT UNIQUE NOT NULL,\n        name TEXT NOT NULL,\n        mtime REAL NOT NULL,\n        size INTEGER NOT NULL,\n        width INTEGER,\n        height INTEGER,\n        seed TEXT,\n        model TEXT,\n        source TEXT,\n        description TEXT,\n        metadata_json TEXT\n    );",
    "CREATE TABLE IF NOT EXISTS tags (\n        id INTEGER PRIMARY KEY,\n        image_id INTEGER NOT NULL,\n        tag TEXT NOT NULL,\n        norm TEXT NOT NULL,\n        kind TEXT NOT NULL,\n        emphasis TEXT NOT NULL,\n        weight REAL NOT NULL,\n        raw TEXT NOT NULL,\n        FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE\n    );",
    "CREATE VIRTUAL TABLE IF NOT EXISTS tag_index USING fts5(\n        norm,\n        tag,\n        kind UNINDEXED,\n        image_id UNINDEXED,\n        tokenize=\"unicode61 tokenchars '_.:-'\"\n    );",
    "CREATE TRIGGER IF NOT EXISTS tags_ai AFTER INSERT ON tags BEGIN\n        INSERT INTO tag_index(rowid, norm, tag, kind, image_id)\n        VALUES (new.id, new.norm, new.tag, new.kind, CAST(new.image_id AS TEXT));\n    END;",
    "CREATE TRIGGER IF NOT EXISTS tags_ad AFTER DELETE ON tags BEGIN\n        INSERT INTO tag_index(tag_index, rowid) VALUES('delete', old.id);\n    END;",
    "CREATE TRIGGER IF NOT EXISTS tags_au AFTER UPDATE ON tags BEGIN\n        INSERT INTO tag_index(tag_index, rowid) VALUES('delete', old.id);\n        INSERT INTO tag_index(rowid, norm, tag, kind, image_id)\n        VALUES (new.id, new.norm, new.tag, new.kind, CAST(new.image_id AS TEXT));\n    END;",
    "CREATE TABLE IF NOT EXISTS clip_embeddings (\n        image_id INTEGER PRIMARY KEY,\n        model TEXT NOT NULL,\n        status TEXT NOT NULL DEFAULT 'pending',\n        vector BLOB,\n        queued_at REAL NOT NULL,\n        updated_at REAL NOT NULL,\n        error TEXT,\n        FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE\n    );",
    "CREATE INDEX IF NOT EXISTS clip_embeddings_status_idx ON clip_embeddings(status, model);",
]


class LocalBooruDatabase:
    """Wrap the SQLite database and expose helpers for images, tags, and CLIP data."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._ensure_schema()

    def close(self) -> None:
        self._connection.commit()
        self._connection.close()

    @property
    def connection(self) -> sqlite3.Connection:
        return self._connection

    def cursor(self) -> sqlite3.Cursor:
        return self._connection.cursor()

    def new_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with closing(self._connection.cursor()) as cur:
            for stmt in SCHEMA_STATEMENTS:
                cur.execute(stmt)
            cols = {row[1] for row in cur.execute("PRAGMA table_info(images)")}
            if "description" not in cols:
                cur.execute("ALTER TABLE images ADD COLUMN description TEXT")
            self._connection.commit()

    # --- Image + tag operations ---------------------------------------------------------

    def lookup_image(self, rel_path: str) -> Optional[sqlite3.Row]:
        return self._connection.execute(
            "SELECT * FROM images WHERE path = ?",
            (rel_path,),
        ).fetchone()

    def upsert_image_record(
        self,
        rel_path: str,
        name: str,
        mtime: float,
        size: int,
        width: Optional[int],
        height: Optional[int],
        seed: Optional[str],
        model: Optional[str],
        source: Optional[str],
        description: Optional[str],
        metadata_json: Optional[str],
        tags: Sequence[TagRecord],
    ) -> Tuple[int, bool]:
        """Insert or update an image row plus tags.

        Returns (image_id, changed) where `changed` indicates metadata or tags were refreshed.
        """
        with self._connection:  # transactional
            existing = self.lookup_image(rel_path)
            row = (
                rel_path,
                name,
                mtime,
                size,
                width,
                height,
                seed,
                model,
                source,
                description,
                metadata_json,
            )
            changed = True
            if existing:
                if abs(existing["mtime"] - mtime) < 1e-6 and existing["size"] == size:
                    changed = False
                else:
                    self._connection.execute(
                        "UPDATE images SET path=?, name=?, mtime=?, size=?, width=?, height=?, seed=?, model=?, source=?, description=?, metadata_json=? WHERE id=?",
                        row + (existing["id"],),
                    )
                image_id = existing["id"]
                if changed:
                    self._connection.execute("DELETE FROM tags WHERE image_id=?", (image_id,))
            else:
                self._connection.execute(
                    "INSERT INTO images(path, name, mtime, size, width, height, seed, model, source, description, metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    row,
                )
                image_id = self._connection.execute("SELECT id FROM images WHERE path=?", (rel_path,)).fetchone()[0]
                changed = True
            if changed:
                for tag in tags:
                    self._connection.execute(
                        "INSERT INTO tags(image_id, tag, norm, kind, emphasis, weight, raw) VALUES (?,?,?,?,?,?,?)",
                        (image_id, tag.tag, tag.norm, tag.kind, tag.emphasis, tag.weight, tag.raw),
                    )
        return image_id, changed

    def delete_missing_images(self, existing_paths: Iterable[str]) -> int:
        existing = list(existing_paths)
        placeholder = ",".join("?" for _ in existing)
        if not placeholder:
            return 0
        sql = f"DELETE FROM images WHERE path NOT IN ({placeholder})"
        with self._connection:
            cur = self._connection.execute(sql, tuple(existing))
            return cur.rowcount

    # --- CLIP embedding operations ------------------------------------------------------

    def ensure_clip_entry(self, image_id: int, model: str, force_reset: bool = False) -> None:
        now = time.time()
        with self._connection:
            row = self._connection.execute(
                "SELECT model, status FROM clip_embeddings WHERE image_id=?",
                (image_id,),
            ).fetchone()
            if row is None:
                self._connection.execute(
                    "INSERT INTO clip_embeddings(image_id, model, status, queued_at, updated_at) VALUES (?,?,?,?,?)",
                    (image_id, model, "pending", now, now),
                )
            else:
                status = row["status"]
                if force_reset or row["model"] != model or status in {"error", "missing"}:
                    self._connection.execute(
                        "UPDATE clip_embeddings SET model=?, status='pending', vector=NULL, error=NULL, queued_at=?, updated_at=? WHERE image_id=?",
                        (model, now, now, image_id),
                    )

    def reserve_clip_batch(self, model: str, limit: int) -> List[sqlite3.Row]:
        with self._connection:
            rows = self._connection.execute(
                "SELECT ce.image_id, i.path, i.mtime FROM clip_embeddings ce JOIN images i ON i.id = ce.image_id "
                "WHERE ce.status = 'pending' AND ce.model = ? ORDER BY ce.queued_at ASC LIMIT ?",
                (model, limit),
            ).fetchall()
            if not rows:
                return []
            now = time.time()
            self._connection.executemany(
                "UPDATE clip_embeddings SET status='processing', updated_at=? WHERE image_id=?",
                ((now, row["image_id"]) for row in rows),
            )
            return rows

    def mark_clip_error(self, image_id: int, message: str) -> None:
        with self._connection:
            now = time.time()
            self._connection.execute(
                "UPDATE clip_embeddings SET status='error', error=?, updated_at=? WHERE image_id=?",
                (message[:512], now, image_id),
            )

    def store_clip_vector(self, image_id: int, model: str, vector: bytes) -> None:
        now = time.time()
        with self._connection:
            self._connection.execute(
                "UPDATE clip_embeddings SET status='ready', model=?, vector=?, error=NULL, updated_at=? WHERE image_id=?",
                (model, vector, now, image_id),
            )

    def clip_progress_counts(self, model: str) -> Tuple[int, int, int]:
        row = self._connection.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN status='ready' THEN 1 ELSE 0 END) AS completed, "
            "SUM(CASE WHEN status='processing' THEN 1 ELSE 0 END) AS processing "
            "FROM clip_embeddings WHERE model=?",
            (model,),
        ).fetchone()
        total = row["total"] or 0
        completed = row["completed"] or 0
        processing = row["processing"] or 0
        return int(total), int(completed), int(processing)

    def iter_clip_vectors(self, model: str) -> Iterator[sqlite3.Row]:
        cur = self._connection.execute(
            "SELECT ce.image_id, ce.vector FROM clip_embeddings ce WHERE ce.status='ready' AND ce.model=?",
            (model,),
        )
        for row in cur:
            yield row

    def purge_clip_vectors(self, model: str) -> None:
        with self._connection:
            self._connection.execute("DELETE FROM clip_embeddings WHERE model=?", (model,))
