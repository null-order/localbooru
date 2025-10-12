"""SQLite persistence layer for localbooru."""

from __future__ import annotations

import json
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
    "CREATE TABLE IF NOT EXISTS images (\n"
    "    id INTEGER PRIMARY KEY,\n"
    "    path TEXT UNIQUE NOT NULL,\n"
    "    name TEXT NOT NULL,\n"
    "    mtime REAL NOT NULL,\n"
    "    size INTEGER NOT NULL,\n"
    "    width INTEGER,\n"
    "    height INTEGER,\n"
    "    seed TEXT,\n"
    "    model TEXT,\n"
    "    source TEXT,\n"
    "    description TEXT,\n"
    "    metadata_json TEXT\n"
    ");",
    "CREATE TABLE IF NOT EXISTS tags (\n"
    "    id INTEGER PRIMARY KEY,\n"
    "    image_id INTEGER NOT NULL,\n"
    "    tag TEXT NOT NULL,\n"
    "    norm TEXT NOT NULL,\n"
    "    kind TEXT NOT NULL,\n"
    "    emphasis TEXT NOT NULL,\n"
    "    weight REAL NOT NULL,\n"
    "    raw TEXT NOT NULL,\n"
    "    source TEXT NOT NULL DEFAULT 'embedded',\n"
    "    FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE\n"
    ");",
    "CREATE INDEX IF NOT EXISTS tags_kind_norm_idx ON tags(kind, norm);",
    "CREATE INDEX IF NOT EXISTS tags_kind_norm_image_idx ON tags(kind, norm, image_id);",
    "CREATE VIRTUAL TABLE IF NOT EXISTS tag_index USING fts5(\n"
    "    norm,\n"
    "    tag,\n"
    "    kind UNINDEXED,\n"
    "    image_id UNINDEXED,\n"
    "    tokenize=\"unicode61 tokenchars '_.:-'\"\n"
    ");",
    "CREATE TABLE IF NOT EXISTS clip_embeddings (\n"
    "    image_id INTEGER PRIMARY KEY,\n"
    "    model TEXT NOT NULL,\n"
    "    status TEXT NOT NULL,\n"
    "    vector BLOB,\n"
    "    error TEXT,\n"
    "    queued_at REAL NOT NULL,\n"
    "    updated_at REAL NOT NULL,\n"
    "    FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE\n"
    ");",
    "CREATE TABLE IF NOT EXISTS auto_tag_jobs (\n"
    "    image_id INTEGER PRIMARY KEY,\n"
    "    status TEXT NOT NULL,\n"
    "    model TEXT NOT NULL,\n"
    "    error TEXT,\n"
    "    queued_at REAL NOT NULL,\n"
    "    updated_at REAL NOT NULL,\n"
    "    FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE\n"
    ");",
    "CREATE TABLE IF NOT EXISTS rating_jobs (\n"
    "    image_id INTEGER PRIMARY KEY,\n"
    "    status TEXT NOT NULL,\n"
    "    model TEXT NOT NULL,\n"
    "    rating TEXT,\n"
    "    confidence REAL,\n"
    "    scores_json TEXT,\n"
    "    error TEXT,\n"
    "    queued_at REAL NOT NULL,\n"
    "    updated_at REAL NOT NULL,\n"
    "    FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE\n"
    ");",
    "DROP TRIGGER IF EXISTS tags_ai;",
    "DROP TRIGGER IF EXISTS tags_ad;",
    "DROP TRIGGER IF EXISTS tags_au;",
    "CREATE TRIGGER IF NOT EXISTS tags_ai AFTER INSERT ON tags BEGIN\n"
    "    INSERT INTO tag_index(rowid, norm, tag, kind, image_id)\n"
    "    VALUES (new.id, new.norm, new.tag, new.kind, new.image_id);\n"
    "END;",
    "CREATE TRIGGER IF NOT EXISTS tags_ad AFTER DELETE ON tags BEGIN\n"
    "    INSERT INTO tag_index(tag_index, rowid, norm, tag, kind, image_id)\n"
    "    VALUES ('delete', old.id, old.norm, old.tag, old.kind, old.image_id);\n"
    "END;",
    "CREATE TRIGGER IF NOT EXISTS tags_au AFTER UPDATE ON tags BEGIN\n"
    "    INSERT INTO tag_index(tag_index, rowid, norm, tag, kind, image_id)\n"
    "    VALUES ('delete', old.id, old.norm, old.tag, old.kind, old.image_id);\n"
    "    INSERT INTO tag_index(rowid, norm, tag, kind, image_id)\n"
    "    VALUES (new.id, new.norm, new.tag, new.kind, new.image_id);\n"
    "END;",
]


class LocalBooruDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._connection = self.new_connection()
        self._ensure_schema()

    def close(self) -> None:
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
            if "rating" not in cols:
                cur.execute("ALTER TABLE images ADD COLUMN rating TEXT")
            if "rating_confidence" not in cols:
                cur.execute("ALTER TABLE images ADD COLUMN rating_confidence REAL")
            if "rating_updated" not in cols:
                cur.execute("ALTER TABLE images ADD COLUMN rating_updated REAL")
            tag_cols = {row[1] for row in cur.execute("PRAGMA table_info(tags)")}
            if "source" not in tag_cols:
                cur.execute(
                    "ALTER TABLE tags ADD COLUMN source TEXT NOT NULL DEFAULT 'embedded'"
                )
            # Normalize legacy rating tag norms from 'rating:explicit' -> 'explicit'
            cur.execute(
                "UPDATE tags SET norm=substr(norm, 8) WHERE kind='rating' AND norm LIKE 'rating:%'"
            )
            rating_job_cols = {
                row[1] for row in cur.execute("PRAGMA table_info(rating_jobs)")
            }
            if "scores_json" not in rating_job_cols:
                cur.execute("ALTER TABLE rating_jobs ADD COLUMN scores_json TEXT")
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
            if existing is None:
                cur = self._connection.execute(
                    "INSERT INTO images "
                    "(path, name, mtime, size, width, height, seed, model, source, description, metadata_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    row,
                )
                image_id = cur.lastrowid
                changed = True
            else:
                cur = self._connection.execute(
                    "UPDATE images SET "
                    "name=?, mtime=?, size=?, width=?, height=?, seed=?, model=?, source=?, description=?, metadata_json=? "
                    "WHERE path=?",
                    (*row, rel_path),
                )
                image_id = existing["id"]
                changed = cur.rowcount > 0

            if not tags:
                self._connection.execute(
                    "DELETE FROM tags WHERE image_id=?",
                    (image_id,),
                )
                return image_id, changed

            existing_tags = set(
                row["norm"]
                for row in self._connection.execute(
                    "SELECT norm FROM tags WHERE image_id=?",
                    (image_id,),
                )
            )
            new_norms = {tag.norm for tag in tags}

            to_delete = existing_tags - new_norms
            to_insert = new_norms - existing_tags
            to_update = existing_tags & new_norms

            if to_delete:
                self._connection.execute(
                    "DELETE FROM tags WHERE image_id=? AND norm IN ({})".format(
                        ",".join("?" * len(to_delete))
                    ),
                    (image_id, *to_delete),
                )

            for tag in tags:
                if tag.norm in to_insert:
                    self._connection.execute(
                        "INSERT INTO tags "
                        "(image_id, tag, norm, kind, emphasis, weight, raw, source) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            image_id,
                            tag.tag,
                            tag.norm,
                            tag.kind,
                            tag.emphasis,
                            tag.weight,
                            tag.raw,
                            tag.source or "embedded",
                        ),
                    )
                elif tag.norm in to_update:
                    self._connection.execute(
                        "UPDATE tags SET "
                        "tag=?, kind=?, emphasis=?, weight=?, raw=?, source=? "
                        "WHERE image_id=? AND norm=?",
                        (
                            tag.tag,
                            tag.kind,
                            tag.emphasis,
                            tag.weight,
                            tag.raw,
                            tag.source or "embedded",
                            image_id,
                            tag.norm,
                        ),
                    )

            changed = changed or bool(to_delete or to_insert or to_update)

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

    def ensure_clip_entry(
        self, image_id: int, model: str, force_reset: bool = False
    ) -> None:
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
                if (
                    force_reset
                    or row["model"] != model
                    or status in {"error", "missing"}
                ):
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

    def mark_clip_error(self, image_id: int, error: str) -> None:
        now = time.time()
        self._connection.execute(
            "UPDATE clip_embeddings SET status='error', error=?, updated_at=? WHERE image_id=?",
            (error, now, image_id),
        )

    def store_clip_vector(self, image_id: int, model: str, vector: bytes) -> None:
        now = time.time()
        conn = self.new_connection()
        try:
            with conn:
                conn.execute(
                    "UPDATE clip_embeddings SET status='ready', model=?, vector=?, updated_at=? WHERE image_id=?",
                    (model, vector, now, image_id),
                )
        finally:
            conn.close()

    def clip_progress_counts(self, model: str) -> Tuple[int, int, int, int]:
        row = self._connection.execute(
            "SELECT "
            "COUNT(*) AS total, "
            "SUM(CASE WHEN status='ready' THEN 1 ELSE 0 END) AS completed, "
            "SUM(CASE WHEN status IN ('pending', 'processing') THEN 1 ELSE 0 END) AS processing, "
            "SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors "
            "FROM clip_embeddings WHERE model=?",
            (model,),
        ).fetchone()
        return (
            row["total"] or 0,
            row["completed"] or 0,
            row["processing"] or 0,
            row["errors"] or 0,
        )

    def iter_clip_vectors(self, model: str) -> Iterator[Tuple[int, bytes]]:
        for row in self._connection.execute(
            "SELECT image_id, vector FROM clip_embeddings WHERE model=? AND status='ready' AND vector IS NOT NULL",
            (model,),
        ):
            yield row["image_id"], row["vector"]

    def purge_clip_vectors(self, model: str) -> None:
        self._connection.execute(
            "DELETE FROM clip_embeddings WHERE model=?",
            (model,),
        )

    def fetch_clip_vector(self, image_id: int, model: str) -> Optional[bytes]:
        row = self._connection.execute(
            "SELECT vector FROM clip_embeddings WHERE image_id=? AND model=? AND status='ready'",
            (image_id, model),
        ).fetchone()
        return row["vector"] if row else None

    def has_ready_clip(self, image_id: int, model: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM clip_embeddings WHERE image_id=? AND model=? AND status='ready'",
            (image_id, model),
        ).fetchone()
        return bool(row and row["status"] == "ready")

    # --- Auto-tag operations ---------------------------------------------------------

    def ensure_auto_tag_job(
        self, image_id: int, model: str, force_reset: bool = False
    ) -> None:
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
                    ((now, row["image_id"]) for row in rows),
                )
                return rows
        finally:
            conn.close()

    def _execute_auto_job_update(self, sql: str, params: Tuple) -> None:
        self._connection.execute(sql, params)

    def mark_auto_tag_ready(self, image_id: int) -> None:
        now = time.time()
        self._execute_auto_job_update(
            "UPDATE auto_tag_jobs SET status='ready', error=NULL, updated_at=? WHERE image_id=?",
            (now, image_id),
        )

    def mark_auto_tag_skipped(self, image_id: int) -> None:
        now = time.time()
        self._connection.execute(
            "UPDATE auto_tag_jobs SET status='skipped', updated_at=? WHERE image_id=?",
            (now, image_id),
        )

    def mark_auto_tag_error(self, image_id: int, error: str) -> None:
        now = time.time()
        self._connection.execute(
            "UPDATE auto_tag_jobs SET status='error', error=?, updated_at=? WHERE image_id=?",
            (error, now, image_id),
        )

    def apply_auto_tags(
        self,
        image_id: int,
        tags: Sequence[TagRecord],
        strategy: str,
        rating_scores: Optional[Dict[str, float]] = None,
    ) -> str:
        result = "skipped"
        with self._connection:
            row = self._connection.execute(
                "SELECT path FROM images WHERE id=?",
                (image_id,),
            ).fetchone()
            if not row:
                return "missing"

            existing_tags = {
                (tag["norm"], tag["kind"])
                for tag in self._connection.execute(
                    "SELECT norm, kind FROM tags WHERE image_id=?",
                    (image_id,),
                )
            }

            if strategy == "missing":
                # Only add tags not already present (by norm+kind)
                to_add = [
                    tag
                    for tag in tags
                    if (tag.norm, tag.kind) not in existing_tags and tag.weight >= 0.0
                ]
                if not to_add:
                    return "skipped"
            else:  # "augment"
                to_add = [tag for tag in tags if tag.weight >= 0.0]

            if not to_add:
                return "skipped"

            # Insert new tags
            for tag in to_add:
                self._connection.execute(
                    "INSERT INTO tags "
                    "(image_id, tag, norm, kind, emphasis, weight, raw, source) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        image_id,
                        tag.tag,
                        tag.norm,
                        tag.kind,
                        tag.emphasis,
                        tag.weight,
                        tag.raw,
                        "auto",
                    ),
                )
            result = "applied"

        if rating_scores:
            self.update_rating_from_scores(image_id, rating_scores)

        return result

    def auto_tag_progress_counts(self) -> Tuple[int, int, int, int]:
        with self._connection:
            row = self._connection.execute(
                "SELECT "
                "COUNT(*) AS total, "
                "SUM(CASE WHEN status='ready' THEN 1 ELSE 0 END) AS completed, "
                "SUM(CASE WHEN status IN ('pending', 'processing') THEN 1 ELSE 0 END) AS processing, "
                "SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors "
                "FROM auto_tag_jobs",
                (),
            ).fetchone()
            return (
                row["total"] or 0,
                row["completed"] or 0,
                row["processing"] or 0,
                row["errors"] or 0,
            )

    def rating_counts(self) -> Dict[str, int]:
        rows = self._connection.execute(
            "SELECT norm, COUNT(DISTINCT image_id) AS freq FROM tags WHERE kind='rating' GROUP BY norm",
        ).fetchall()
        return {
            (row["norm"] or "").lower(): int(row["freq"] or 0)
            for row in rows
            if row
        }

    # --- Rating operations ---------------------------------------------------------

    def update_rating_from_scores(
        self,
        image_id: int,
        scores: Dict[str, float],
        *,
        model: str = "wd14",
    ) -> None:
        if not scores:
            return
        normalized = {
            str(label).lower(): float(value)
            for label, value in scores.items()
            if isinstance(value, (int, float))
        }
        if not normalized:
            return
        best_label, best_score = max(normalized.items(), key=lambda item: item[1])
        now = time.time()
        scores_json = json.dumps(normalized, sort_keys=True)
        with self._connection:
            self._connection.execute(
                "UPDATE images SET rating=?, rating_confidence=?, rating_updated=? WHERE id=?",
                (best_label, best_score, now, image_id),
            )
            self._connection.execute(
                """
                INSERT INTO rating_jobs(image_id, status, model, rating, confidence, scores_json, error, queued_at, updated_at)
                VALUES (?, 'ready', ?, ?, ?, ?, NULL, ?, ?)
                ON CONFLICT(image_id) DO UPDATE SET
                    status=excluded.status,
                    model=excluded.model,
                    rating=excluded.rating,
                    confidence=excluded.confidence,
                    scores_json=excluded.scores_json,
                    error=NULL,
                    updated_at=excluded.updated_at
                """,
                (image_id, model, best_label, best_score, scores_json, now, now),
            )

    def store_rating(
        self,
        image_id: int,
        rating: str,
        confidence: float,
        scores: Optional[Dict[str, float]] = None,
    ) -> None:
        now = time.time()
        existing_scores_json = None
        row = self._connection.execute(
            "SELECT scores_json FROM rating_jobs WHERE image_id=?",
            (image_id,),
        ).fetchone()
        if row and row["scores_json"]:
            existing_scores_json = row["scores_json"]

        if scores and isinstance(scores, dict):
            normalized = {
                str(label).lower(): float(value)
                for label, value in scores.items()
                if isinstance(value, (int, float))
            }
            scores_json = json.dumps(normalized, sort_keys=True)
        else:
            scores_json = existing_scores_json

        with self._connection:
            self._connection.execute(
                "UPDATE images SET rating=?, rating_confidence=?, rating_updated=? WHERE id=?",
                (rating, confidence, now, image_id),
            )
            self._connection.execute(
                "DELETE FROM tags WHERE image_id=? AND kind='rating' AND source!='auto'",
                (image_id,),
            )
            tag = f"rating:{rating}"
            norm = rating.lower()
            raw_value = f"dbrating:{tag}:{confidence:.3f}"
            self._connection.execute(
                """INSERT INTO tags
                   (image_id, tag, norm, kind, emphasis, weight, raw, source)
                   VALUES (?, ?, ?, 'rating', 'normal', ?, ?, 'dbrating')""",
                (image_id, tag, norm, confidence, raw_value),
            )
            self._connection.execute(
                "UPDATE rating_jobs SET rating=?, confidence=?, scores_json=?, updated_at=? WHERE image_id=?",
                (rating, confidence, scores_json, now, image_id),
            )

    # --- Query helpers -----------------------------------------------------------------

    def get_auto_job_status(self, image_id: int) -> Optional[str]:
        row = self._connection.execute(
            "SELECT status FROM auto_tag_jobs WHERE image_id=?",
            (image_id,),
        ).fetchone()
        return row["status"] if row else None

    def has_auto_tags(self, image_id: int) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM tags WHERE image_id=? AND source='auto' LIMIT 1",
            (image_id,),
        ).fetchone()
        return bool(row)

    def has_rating_tag(self, image_id: int) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM tags WHERE image_id=? AND kind='rating' LIMIT 1",
            (image_id,),
        ).fetchone()
        return bool(row)

    def get_auto_job_details(self, image_id: int) -> Optional[Dict[str, object]]:
        row = self._connection.execute(
            "SELECT status, model, error, queued_at, updated_at FROM auto_tag_jobs WHERE image_id=?",
            (image_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "status": row["status"],
            "model": row["model"],
            "error": row["error"],
            "queued_at": row["queued_at"],
            "updated_at": row["updated_at"],
        }

    def load_auto_tag_jobs(self) -> Dict[int, Tuple[str, Optional[str]]]:
        jobs: Dict[int, Tuple[str, Optional[str]]] = {}
        for row in self._connection.execute(
            "SELECT image_id, status, model FROM auto_tag_jobs",
            (),
        ):
            jobs[row["image_id"]] = (row["status"], row["model"])
        return jobs

    def load_auto_tagged_ids(self) -> Set[int]:
        return {
            row["image_id"]
            for row in self._connection.execute(
                "SELECT DISTINCT image_id FROM tags WHERE source='auto'",
                (),
            )
        }

    # --- General query helpers ---------------------------------------------------------

    def iter_image_paths(self) -> Iterator[str]:
        for row in self._connection.execute(
            "SELECT path FROM images ORDER BY mtime DESC"
        ):
            yield row["path"]

    def iter_images(self, limit: int = 0, offset: int = 0) -> Iterator[sqlite3.Row]:
        sql = "SELECT * FROM images ORDER BY mtime DESC, id DESC"
        params = ()
        if limit > 0:
            sql += " LIMIT ? OFFSET ?"
            params = (limit, offset)
        for row in self._connection.execute(sql, params):
            yield row
