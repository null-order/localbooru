"""SQLite persistence layer for localbooru."""
from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple

from .tags import TagRecord

SCHEMA_STATEMENTS = [
    "PRAGMA journal_mode=WAL;",
    "PRAGMA synchronous=NORMAL;",
    "PRAGMA foreign_keys = ON;",
    "CREATE TABLE IF NOT EXISTS images (\n        id INTEGER PRIMARY KEY,\n        path TEXT UNIQUE NOT NULL,\n        name TEXT NOT NULL,\n        mtime REAL NOT NULL,\n        size INTEGER NOT NULL,\n        width INTEGER,\n        height INTEGER,\n        seed TEXT,\n        model TEXT,\n        source TEXT,\n        description TEXT,\n        metadata_json TEXT\n    );",
    "CREATE TABLE IF NOT EXISTS tags (\n        id INTEGER PRIMARY KEY,\n        image_id INTEGER NOT NULL,\n        tag TEXT NOT NULL,\n        norm TEXT NOT NULL,\n        kind TEXT NOT NULL,\n        emphasis TEXT NOT NULL,\n        weight REAL NOT NULL,\n        raw TEXT NOT NULL,\n        source TEXT NOT NULL DEFAULT 'embedded',\n        FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE\n    );",
    "CREATE VIRTUAL TABLE IF NOT EXISTS tag_index USING fts5(\n        norm,\n        tag,\n        kind UNINDEXED,\n        image_id UNINDEXED,\n        tokenize=\"unicode61 tokenchars '_.:-'\"\n    );",
    "DROP TRIGGER IF EXISTS tags_ai;",
    "DROP TRIGGER IF EXISTS tags_ad;",
    "DROP TRIGGER IF EXISTS tags_au;",
    "CREATE TRIGGER tags_ai AFTER INSERT ON tags BEGIN\n        INSERT INTO tag_index(rowid, norm, tag, kind, image_id)\n        VALUES (new.id, new.norm, new.tag, new.kind, CAST(new.image_id AS TEXT));\n    END;",
    "CREATE TRIGGER tags_ad AFTER DELETE ON tags BEGIN\n        DELETE FROM tag_index WHERE rowid = old.id;\n    END;",
    "CREATE TRIGGER tags_au AFTER UPDATE ON tags BEGIN\n        DELETE FROM tag_index WHERE rowid = old.id;\n        INSERT INTO tag_index(rowid, norm, tag, kind, image_id)\n        VALUES (new.id, new.norm, new.tag, new.kind, CAST(new.image_id AS TEXT));\n    END;",
    "CREATE TABLE IF NOT EXISTS clip_embeddings (\n        image_id INTEGER PRIMARY KEY,\n        model TEXT NOT NULL,\n        status TEXT NOT NULL DEFAULT 'pending',\n        vector BLOB,\n        queued_at REAL NOT NULL,\n        updated_at REAL NOT NULL,\n        error TEXT,\n        FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE\n    );",
    "CREATE INDEX IF NOT EXISTS clip_embeddings_status_idx ON clip_embeddings(status, model);",
    "CREATE TABLE IF NOT EXISTS auto_tag_jobs (\n        image_id INTEGER PRIMARY KEY,\n        status TEXT NOT NULL DEFAULT 'pending',\n        model TEXT,\n        queued_at REAL NOT NULL,\n        updated_at REAL NOT NULL,\n        error TEXT,\n        FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE\n    );",
    "CREATE INDEX IF NOT EXISTS auto_tag_jobs_status_idx ON auto_tag_jobs(status);",
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
            tag_cols = {row[1] for row in cur.execute("PRAGMA table_info(tags)")}
            if "source" not in tag_cols:
                cur.execute("ALTER TABLE tags ADD COLUMN source TEXT NOT NULL DEFAULT 'embedded'")
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
                        "INSERT INTO tags(image_id, tag, norm, kind, emphasis, weight, raw, source) VALUES (?,?,?,?,?,?,?,?)",
                        (
                            image_id,
                            tag.tag,
                            tag.norm,
                            tag.kind,
                            tag.emphasis,
                            tag.weight,
                            tag.raw,
                            getattr(tag, "source", "embedded"),
                        ),
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
        conn = self.new_connection()
        try:
            with conn:
                rows = conn.execute(
                    "SELECT ce.image_id, i.path, i.mtime FROM clip_embeddings ce JOIN images i ON i.id = ce.image_id "
                    "WHERE ce.status = 'pending' AND ce.model = ? ORDER BY ce.queued_at ASC LIMIT ?",
                    (model, limit),
                ).fetchall()
                if not rows:
                    return []
                now = time.time()
                conn.executemany(
                    "UPDATE clip_embeddings SET status='processing', updated_at=? WHERE image_id=?",
                    ((now, row["image_id"]) for row in rows),
                )
                return rows
        finally:
            conn.close()

    def mark_clip_error(self, image_id: int, message: str) -> None:
        with self._connection:
            now = time.time()
            self._connection.execute(
                "UPDATE clip_embeddings SET status='error', error=?, updated_at=? WHERE image_id=?",
                (message[:512], now, image_id),
            )

    def store_clip_vector(self, image_id: int, model: str, vector: bytes) -> None:
        now = time.time()
        conn = self.new_connection()
        try:
            with conn:
                conn.execute(
                    "UPDATE clip_embeddings SET status='ready', model=?, vector=?, error=NULL, updated_at=? WHERE image_id=?",
                    (model, vector, now, image_id),
                )
        finally:
            conn.close()

    def clip_progress_counts(self, model: str) -> Tuple[int, int, int, int]:
        row = self._connection.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN status='ready' THEN 1 ELSE 0 END) AS completed, "
            "SUM(CASE WHEN status='processing' THEN 1 ELSE 0 END) AS processing, "
            "SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors "
            "FROM clip_embeddings WHERE model=?",
            (model,),
        ).fetchone()
        total = int(row["total"] or 0)
        completed = int(row["completed"] or 0)
        processing = int(row["processing"] or 0)
        errors = int(row["errors"] or 0)
        return total, completed, processing, errors

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

    def fetch_clip_vector(self, image_id: int, model: str) -> Optional[bytes]:
        row = self._connection.execute(
            "SELECT vector FROM clip_embeddings WHERE image_id=? AND model=? AND status='ready'",
            (image_id, model),
        ).fetchone()
        if row is None:
            return None
        return row["vector"]

    def has_ready_clip(self, image_id: int, model: str) -> bool:
        row = self._connection.execute(
            "SELECT status FROM clip_embeddings WHERE image_id=? AND model=?",
            (image_id, model),
        ).fetchone()
        return bool(row and row["status"] == "ready")

    # --- Auto-tag operations ---------------------------------------------------------

    def ensure_auto_tag_job(self, image_id: int, model: str, force_reset: bool = False) -> None:
        now = time.time()
        with self._connection:
            row = self._connection.execute(
                "SELECT status, model FROM auto_tag_jobs WHERE image_id=?",
                (image_id,),
            ).fetchone()
            if row is None:
                self._connection.execute(
                    "INSERT INTO auto_tag_jobs(image_id, status, model, queued_at, updated_at) VALUES (?,?,?,?,?)",
                    (image_id, "pending", model, now, now),
                )
            else:
                status = row["status"]
                stored_model = row["model"]
                reset_needed = False
                if force_reset:
                    reset_needed = True
                elif stored_model != model:
                    reset_needed = True
                elif status in {"error", "missing"}:
                    reset_needed = True

                if reset_needed:
                    self._connection.execute(
                        "UPDATE auto_tag_jobs SET status='pending', model=?, error=NULL, queued_at=?, updated_at=? WHERE image_id=?",
                        (model, now, now, image_id),
                    )

    def reserve_auto_tag_batch(self, limit: int) -> List[sqlite3.Row]:
        conn = self.new_connection()
        try:
            with conn:
                rows = conn.execute(
                    "SELECT j.image_id, i.path FROM auto_tag_jobs j "
                    "JOIN images i ON i.id = j.image_id "
                    "WHERE j.status = 'pending' ORDER BY j.queued_at ASC LIMIT ?",
                    (limit,),
                ).fetchall()
                if not rows:
                    return []
                now = time.time()
                conn.executemany(
                    "UPDATE auto_tag_jobs SET status='processing', updated_at=? WHERE image_id=?",
                    [(now, row["image_id"]) for row in rows],
                )
                return rows
        finally:
            conn.close()

    def _execute_auto_job_update(self, sql: str, params: Sequence[object]) -> None:
        conn = self.new_connection()
        try:
            with conn:
                conn.execute(sql, params)
        finally:
            conn.close()

    def mark_auto_tag_ready(self, image_id: int) -> None:
        now = time.time()
        self._execute_auto_job_update(
            "UPDATE auto_tag_jobs SET status='ready', error=NULL, updated_at=? WHERE image_id=?",
            (now, image_id),
        )

    def mark_auto_tag_skipped(self, image_id: int) -> None:
        now = time.time()
        self._execute_auto_job_update(
            "UPDATE auto_tag_jobs SET status='skipped', updated_at=? WHERE image_id=?",
            (now, image_id),
        )

    def mark_auto_tag_error(self, image_id: int, message: str) -> None:
        now = time.time()
        self._execute_auto_job_update(
            "UPDATE auto_tag_jobs SET status='error', error=?, updated_at=? WHERE image_id=?",
            (message[:512], now, image_id),
        )

    def apply_auto_tags(
        self,
        image_id: int,
        tags: Sequence[TagRecord],
        *,
        strategy: str,
    ) -> str:
        mode = (strategy or "missing").lower()
        with self._connection:
            manual_pairs = {
                (row["kind"], row["norm"])
                for row in self._connection.execute(
                    "SELECT kind, norm FROM tags WHERE image_id=? AND source <> 'auto'",
                    (image_id,),
                )
            }

            if mode != "augment" and manual_pairs:
                return "skipped"

            current_auto = {
                (row["kind"], row["norm"]): (
                    row["tag"],
                    float(row["weight"] or 0.0),
                    row["emphasis"],
                    row["raw"],
                )
                for row in self._connection.execute(
                    "SELECT kind, norm, tag, weight, emphasis, raw FROM tags WHERE image_id=? AND source='auto'",
                    (image_id,),
                )
            }

            normalized_new: Dict[tuple[str, str], tuple[str, float, str, str]] = {}
            for tag in tags:
                key = (tag.kind, tag.norm)
                if key in normalized_new or key in manual_pairs:
                    continue
                normalized_new[key] = (
                    tag.tag,
                    float(tag.weight),
                    tag.emphasis,
                    tag.raw,
                )

            if normalized_new == current_auto:
                return "empty"

            self._connection.execute(
                "DELETE FROM tags WHERE image_id=? AND source=?",
                (image_id, "auto"),
            )

            existing = set(manual_pairs)
            inserted = 0
            for (kind, norm), (tag_value, weight_value, emphasis_value, raw_value) in normalized_new.items():
                if (kind, norm) in existing:
                    continue
                self._connection.execute(
                    "INSERT INTO tags(image_id, tag, norm, kind, emphasis, weight, raw, source) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        image_id,
                        tag_value,
                        norm,
                        kind,
                        emphasis_value,
                        weight_value,
                        raw_value,
                        "auto",
                    ),
                )
                existing.add((kind, norm))
                inserted += 1

            return "updated" if inserted else "empty"

    def auto_tag_progress_counts(self) -> Tuple[int, int, int, int]:
        row = self._connection.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN status IN ('ready', 'skipped') THEN 1 ELSE 0 END) AS completed, "
            "SUM(CASE WHEN status='processing' THEN 1 ELSE 0 END) AS processing, "
            "SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors "
            "FROM auto_tag_jobs",
        ).fetchone()
        total = int(row["total"] or 0)
        completed = int(row["completed"] or 0)
        processing = int(row["processing"] or 0)
        errors = int(row["errors"] or 0)
        return total, completed, processing, errors

    def get_auto_job_status(self, image_id: int) -> Optional[str]:
        row = self._connection.execute(
            "SELECT status FROM auto_tag_jobs WHERE image_id=?",
            (image_id,),
        ).fetchone()
        if row is None:
            return None
        return str(row["status"])

    def has_auto_tags(self, image_id: int) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM tags WHERE image_id=? AND source='auto' LIMIT 1",
            (image_id,),
        ).fetchone()
        return bool(row)

    def get_auto_job_details(self, image_id: int) -> Optional[Dict[str, object]]:
        row = self._connection.execute(
            "SELECT status, queued_at FROM auto_tag_jobs WHERE image_id=?",
            (image_id,),
        ).fetchone()
        if row is None:
            return None
        status = str(row["status"])
        details: Dict[str, object] = {"status": status}
        if status == "pending":
            queued_at = row["queued_at"]
            pos_row = self._connection.execute(
                "SELECT COUNT(*) FROM auto_tag_jobs WHERE status='pending' AND queued_at <= ?",
                (queued_at,),
            ).fetchone()
            details["position"] = int(pos_row[0]) if pos_row else None
        elif status == "processing":
            details["position"] = 0
        else:
            details["position"] = None
        return details

    def load_auto_tag_jobs(self) -> Dict[int, Tuple[str, Optional[str]]]:
        rows = self._connection.execute(
            "SELECT image_id, status, model FROM auto_tag_jobs"
        ).fetchall()
        jobs: Dict[int, Tuple[str, Optional[str]]] = {}
        for row in rows:
            image_id = int(row["image_id"])
            status = str(row["status"])
            model = row["model"]
            jobs[image_id] = (status, model)
        return jobs

    def load_auto_tagged_ids(self) -> Set[int]:
        rows = self._connection.execute(
            "SELECT DISTINCT image_id FROM tags WHERE source='auto'"
        ).fetchall()
        return {int(row["image_id"]) for row in rows}
