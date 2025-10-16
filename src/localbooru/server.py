"""HTTP server for localbooru."""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import logging
import mimetypes
import os
import shutil
import sqlite3
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from email.utils import formatdate
from email.parser import BytesParser
from email.policy import default as default_email_policy

import numpy as np

from .auto_tagging import AutoTagIndexer, AutoTagProgress
from .clip import ClipIndexer, ClipProgress, get_clip_model
from .clip_search import perform_clip_search
from .config import LocalBooruConfig
from .database import LocalBooruDatabase
from .scanner import Scanner
from .metadata import extract_character_details
from .search import (
    autocomplete_tags,
    fetch_tags_for_images,
    matched_image_ids,
    search_images,
    tokens_from_query,
)

LOGGER = logging.getLogger(__name__)

try:  # Pillow optional for thumbnails
    from PIL import Image
except ImportError:  # pragma: no cover - optional dependency
    Image = None  # type: ignore


FACET_KIND_ORDER = {
    "prompt": 0,
    "rating": 0,
    "character": 0,
    "description": 0,
    "negative": 1,
}

RATING_CLASSES = ["general", "sensitive", "questionable", "explicit"]


def _coerce_bool(value, default=True):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"", "0", "false", "no", "off"}:
            return False
        if lowered in {"1", "true", "yes", "on"}:
            return True
    return default


def summarize_facets_from_tag_map(
    tag_map: Dict[int, List[Dict[str, object]]],
) -> List[Dict[str, object]]:
    summary: Dict[Tuple[str, str], Dict[str, object]] = {}
    for tags in tag_map.values():
        if not isinstance(tags, list):
            continue
        seen: Set[Tuple[str, str]] = set()
        for tag in tags:
            if not isinstance(tag, dict):
                continue
            norm = tag.get("norm")
            kind = tag.get("kind")
            if not isinstance(norm, str) or not norm:
                continue
            if not isinstance(kind, str) or not kind:
                continue
            key = (kind, norm)
            if key in seen:
                continue
            seen.add(key)
            label = tag.get("tag")
            label_str = label if isinstance(label, str) and label else norm
            entry = summary.get(key)
            if entry is None:
                entry = {"tag": label_str, "norm": norm, "kind": kind, "freq": 0}
                summary[key] = entry
            entry["freq"] += 1

    def sort_key(item: Dict[str, object]) -> Tuple[int, int, str]:
        kind = item.get("kind")
        kind_rank = FACET_KIND_ORDER.get(kind, 2)
        freq = int(item.get("freq", 0))
        tag_label = item.get("tag")
        tag_str = tag_label if isinstance(tag_label, str) else ""
        return (kind_rank, -freq, tag_str)

    return sorted(summary.values(), key=sort_key)


class LocalBooruRequestHandler(BaseHTTPRequestHandler):
    server_version = "LocalBooru/0.1"

    def _parse_multipart_form(
        self, body: bytes, content_type: str
    ) -> Tuple[Dict[str, List[str]], List[Dict[str, object]]]:
        headers = f"Content-Type: {content_type}\r\n\r\n".encode("utf-8")
        try:
            message = BytesParser(policy=default_email_policy).parsebytes(
                headers + body
            )
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.error("Failed to parse multipart form: %s", exc)
            return {}, []

        fields: Dict[str, List[str]] = {}
        files: List[Dict[str, object]] = []

        if message.get_content_maintype() != "multipart":
            return fields, files

        for part in message.iter_parts():
            if part.get_content_disposition() != "form-data":
                continue
            name = part.get_param("name", header="content-disposition")
            if not name:
                continue
            filename = part.get_filename()
            payload = part.get_payload(decode=True) or b""
            if filename:
                files.append(
                    {
                        "name": name,
                        "filename": filename,
                        "data": payload,
                        "content_type": part.get_content_type(),
                    }
                )
            else:
                charset = part.get_content_charset() or "utf-8"
                try:
                    text = payload.decode(charset, errors="replace")
                except LookupError:
                    text = payload.decode("utf-8", errors="replace")
                fields.setdefault(name, []).append(text)

        return fields, files

    def _build_clip_response(
        self,
        window: List[Tuple[int, float]],
        total: int,
        offset: int,
        limit: int,
        *,
        include_tags: bool,
    ) -> Dict[str, object]:
        if not window:
            return {
                "results": [],
                "total": total,
                "offset": offset,
                "limit": limit,
                "facets": [],
            }

        image_ids = [image_id for image_id, _score in window]
        db: LocalBooruDatabase = self.server.db  # type: ignore[attr-defined]
        conn = db.new_connection()
        tag_map: Dict[int, List[Dict[str, object]]] = {}
        try:
            placeholders = ",".join("?" for _ in image_ids)
            sql = f"SELECT * FROM images WHERE id IN ({placeholders})"
            rows = conn.execute(sql, tuple(image_ids)).fetchall()
            if include_tags:
                tag_map = fetch_tags_for_images(conn, image_ids)
        finally:
            conn.close()

        row_map = {row["id"]: row for row in rows}
        payload_results: List[Dict[str, object]] = []
        for image_id, score in window:
            row = row_map.get(image_id)
            if row is None:
                continue
            payload_results.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "path": row["path"],
                    "file_url": self.file_url_for(row["id"], row["path"]),
                    "thumb_url": self.thumb_url_for(row["id"], row["path"]),
                    "width": row["width"],
                    "height": row["height"],
                    "seed": row["seed"],
                    "model": row["model"] or row["source"],
                    "description": row["description"],
                    "mtime": row["mtime"],
                    "size": row["size"],
                    "score": score,
                    "tags": tag_map.get(row["id"], []) if include_tags else [],
                }
            )

        facets_payload = summarize_facets_from_tag_map(tag_map) if include_tags else []

        return {
            "results": payload_results,
            "total": total,
            "offset": offset,
            "limit": limit,
            "facets": facets_payload,
        }

    def do_GET(self) -> None:  # pragma: no cover - network path
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/":
            self._serve_index()
            return
        if path in {"/app.css", "/app.js"}:
            self._serve_frontend_asset(path.lstrip("/"))
            return

        if self.path == "/api/status/clip":
            self._handle_clip_status()
            return
        elif self.path == "/api/status/auto":
            self._handle_auto_status()
            return
        elif self.path == "/api/rating_status":
            self._handle_rating_status()
            return
        elif self.path == "/api/rating_counts":
            self._handle_rating_counts()
            return

        if path == "/api/images":
            self._handle_images(parsed.query)
            return
        if path.startswith("/api/images/"):
            identifier = path[len("/api/images/") :]
            self._handle_image_detail(identifier)
            return
        if path == "/api/tags":
            self._handle_tags(parsed.query)
            return
        if path == "/api/tag-stats":
            self._handle_tag_stats()
            return
        if path.startswith("/files/"):
            identifier = path[len("/files/") :]
            self._handle_file(identifier)
            return
        if path.startswith("/thumbs/"):
            identifier = path[len("/thumbs/") :]
            self._handle_thumbnail(identifier)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:  # pragma: no cover - network path
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/clip/pause":
            self._handle_clip_control("pause")
            return
        if parsed.path == "/api/clip/resume":
            self._handle_clip_control("resume")
            return
        if parsed.path == "/api/auto/pause":
            self._handle_auto_control("pause")
            return
        if parsed.path == "/api/auto/resume":
            self._handle_auto_control("resume")
            return
        if parsed.path == "/api/search/clip":
            self._handle_clip_search()
            return
        if parsed.path == "/api/search/clip/file":
            self._handle_clip_search_file()
            return
        if parsed.path == "/api/image-tags":
            self._handle_image_tags()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def _handle_clip_status(self) -> None:
        LOGGER.debug("GET /api/status/clip")
        progress: ClipProgress = self.server.progress  # type: ignore[attr-defined]
        payload = progress.snapshot(self.server.db)  # type: ignore[attr-defined]
        config: Optional[LocalBooruConfig] = getattr(self.server, "config", None)
        payload["enabled"] = bool(config and getattr(config, "clip_enabled", False))
        blob = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def _handle_auto_status(self) -> None:
        LOGGER.debug("GET /api/status/auto")
        auto_progress = getattr(self.server, "auto_progress", None)
        if auto_progress is None:
            self._send_json({"enabled": False})
        else:
            db: Optional[LocalBooruDatabase] = getattr(self.server, "db", None)
            self._send_json(auto_progress.snapshot(db))

    def _handle_rating_status(self) -> None:
        if LOGGER.isEnabledFor(logging.DEBUG):
            LOGGER.debug("GET /api/rating_status")
        db: LocalBooruDatabase = self.server.db  # type: ignore[attr-defined]
        total = db.connection.execute("SELECT COUNT(*) FROM images").fetchone()[0]
        counts = self._cached_rating_counts(db)
        tagged = sum(counts.values())
        untagged = max(total - tagged, 0)
        payload = {
            "enabled": True,
            "total": total,
            "tagged": tagged,
            "untagged": untagged,
            "counts": {label: int(counts.get(label, 0)) for label in RATING_CLASSES},
            "state": "complete" if untagged == 0 else "running",
        }
        self._send_json(payload)

    def _handle_rating_counts(self) -> None:
        if LOGGER.isEnabledFor(logging.DEBUG):
            LOGGER.debug("GET /api/rating_counts")
        db: LocalBooruDatabase = self.server.db  # type: ignore[attr-defined]
        counts = self._cached_rating_counts(db)
        payload = {label: int(counts.get(label, 0)) for label in RATING_CLASSES}
        self._send_json({"counts": payload})

    def _cached_rating_counts(self, db: LocalBooruDatabase) -> Dict[str, int]:
        cache = getattr(self.server, "_rating_counts_cache", None)
        now = time.time()
        ttl = 5.0
        if not isinstance(cache, dict) or (now - cache.get("timestamp", 0)) > ttl:
            counts = db.rating_counts()
            cache = {"timestamp": now, "counts": counts}
            setattr(self.server, "_rating_counts_cache", cache)
        cached_counts = cache.get("counts", {})
        if not isinstance(cached_counts, dict):
            return {}
        return dict(cached_counts)

    def _serve_index(self) -> None:
        index_file = Path(__file__).resolve().parent / "frontend" / "index.html"
        if not index_file.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "index.html missing")
            return
        data = index_file.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_frontend_asset(self, filename: str) -> None:
        base_dir = Path(__file__).resolve().parent / "frontend"
        try:
            asset_path = (base_dir / filename).resolve(strict=True)
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND, f"{filename} missing")
            return
        base_resolved = base_dir.resolve()
        if asset_path.parent != base_resolved:
            self.send_error(HTTPStatus.NOT_FOUND, "invalid asset path")
            return
        if not asset_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "asset not found")
            return
        data = asset_path.read_bytes()
        content_type, _encoding = mimetypes.guess_type(asset_path.name)
        if not content_type:
            content_type = "application/octet-stream"
        if content_type.startswith("text/"):
            content_type = f"{content_type}; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle_images(self, query_string: str) -> None:
        params = urllib.parse.parse_qs(query_string)
        query = params.get("q", [""])[0]
        try:
            limit = int(params.get("limit", ["40"])[0])
        except ValueError:
            limit = 40
        try:
            offset = int(params.get("offset", ["0"])[0])
        except ValueError:
            offset = 0

        limit = min(max(limit, 1), 200)
        offset = max(offset, 0)

        db: LocalBooruDatabase = self.server.db  # type: ignore[attr-defined]
        config: LocalBooruConfig = self.server.config  # type: ignore[attr-defined]
        conn = db.new_connection()
        try:
            tokens = tokens_from_query(query)
            rows, total = search_images(conn, tokens, limit, offset, config)

            image_ids = [row["id"] for row in rows]
            tag_map = fetch_tags_for_images(conn, image_ids)
        finally:
            conn.close()

        images = [
            {
                "id": row["id"],
                "name": row["name"],
                "path": row["path"],
                "file_url": self.file_url_for(row["id"], row["path"]),
                "thumb_url": self.thumb_url_for(row["id"], row["path"]),
                "width": row["width"],
                "height": row["height"],
                "seed": row["seed"],
                "model": row["model"] or row["source"],
                "description": row["description"],
                "mtime": row["mtime"],
                "size": row["size"],
                "rating": row["rating"],
                "rating_confidence": row["rating_confidence"],
                "tags": tag_map.get(row["id"], []),
            }
            for row in rows
        ]
        payload = {"images": images, "total": total}
        self._send_json(payload)

    def _handle_tag_stats(self) -> None:
        """Handle /api/tag-stats endpoint with conditional fetching."""
        try:
            tag_stats, last_modified = self.server.get_cached_tag_stats()  # type: ignore[attr-defined]
        except Exception as e:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Cache error: {e}")
            return

        # Support conditional fetching with If-Modified-Since
        if_modified_since = self.headers.get("If-Modified-Since")
        if if_modified_since:
            try:
                from email.utils import parsedate_to_datetime

                client_time = parsedate_to_datetime(if_modified_since).timestamp()
                if last_modified <= client_time:
                    self.send_response(HTTPStatus.NOT_MODIFIED)
                    self.end_headers()
                    return
            except (ValueError, TypeError):
                # Invalid date format, continue with full response
                pass

        payload = {
            "tags": tag_stats,
            "last_modified": last_modified,
            "count": len(tag_stats),
        }

        # Send response with Last-Modified header
        body = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))

        # Add Last-Modified header for conditional requests
        from email.utils import formatdate

        last_modified_str = formatdate(last_modified, usegmt=True)
        self.send_header("Last-Modified", last_modified_str)

        self.end_headers()
        self.wfile.write(body)

    def _handle_tags(self, query_string: str) -> None:
        params = urllib.parse.parse_qs(query_string)
        prefix = params.get("q", [""])[0]
        kind = params.get("kind", [""])[0] or None
        db: LocalBooruDatabase = self.server.db  # type: ignore[attr-defined]
        conn = db.new_connection()
        try:
            tags = autocomplete_tags(conn, prefix, kind)
        finally:
            conn.close()
        self._send_json({"tags": tags})

    def _handle_image_detail(self, identifier: str) -> None:
        try:
            image_id = int(identifier)
        except ValueError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid identifier")
            return

        db: LocalBooruDatabase = self.server.db  # type: ignore[attr-defined]
        conn = db.new_connection()
        clip_row = None
        auto_row = None
        auto_position: Optional[int] = None
        rating_row = None
        rating_position: Optional[int] = None
        try:
            raw_row = conn.execute(
                "SELECT * FROM images WHERE id=?", (image_id,)
            ).fetchone()
            if not raw_row:
                self.send_error(HTTPStatus.NOT_FOUND, "Image not found")
                return
            row_map: Dict[str, object] = {}
            if hasattr(raw_row, "keys"):
                for key in raw_row.keys():  # type: ignore[attr-defined]
                    try:
                        row_map[key] = raw_row[key]
                    except (IndexError, KeyError):
                        continue
            else:
                try:
                    # sqlite rows are sequences; fall back to positional mapping
                    row_map = dict(enumerate(raw_row))  # type: ignore[arg-type]
                except TypeError:
                    row_map = {}

            def row_get(key: str, default=None):
                return row_map.get(key, default)

            tag_rows = conn.execute(
                "SELECT tag, norm, kind, emphasis, weight, raw, source FROM tags WHERE image_id=? ORDER BY kind, tag",
                (image_id,),
            ).fetchall()
            seen_pairs: List[tuple[str, str]] = []
            seen_set: Set[tuple[str, str]] = set()
            for row in tag_rows:
                pair = (row["norm"], row["kind"])
                if pair in seen_set:
                    continue
                seen_set.add(pair)
                seen_pairs.append(pair)
            counts: Dict[tuple[str, str], int] = {}
            if seen_pairs:
                pairs_by_kind: Dict[str, List[str]] = {}
                for norm, kind in seen_pairs:
                    bucket = pairs_by_kind.setdefault(kind, [])
                    bucket.append(norm)
                for kind, norm_list in pairs_by_kind.items():
                    unique_norms = list(dict.fromkeys(norm_list))
                    placeholders = ",".join("?" for _ in unique_norms)
                    sql_counts = (
                        f"SELECT norm, kind, COUNT(DISTINCT image_id) AS freq FROM tags "
                        f"WHERE kind = ? AND norm IN ({placeholders}) "
                        "GROUP BY norm, kind"
                    )
                    params = [kind, *unique_norms]
                    for norm, row_kind, freq in conn.execute(sql_counts, params):
                        counts[(norm, row_kind)] = freq

            clip_row = conn.execute(
                "SELECT status, model, queued_at, updated_at, error FROM clip_embeddings WHERE image_id=?",
                (image_id,),
            ).fetchone()
            auto_row = conn.execute(
                "SELECT status, queued_at, updated_at, model, error FROM auto_tag_jobs WHERE image_id=?",
                (image_id,),
            ).fetchone()
            if auto_row is not None:
                status_value = auto_row["status"]
                queued_value = auto_row["queued_at"]
                if status_value == "pending" and queued_value is not None:
                    pos_row = conn.execute(
                        "SELECT COUNT(*) FROM auto_tag_jobs WHERE status='pending' AND queued_at <= ?",
                        (queued_value,),
                    ).fetchone()
                    if pos_row is not None:
                        auto_position = int(pos_row[0])
            rating_row = conn.execute(
                "SELECT status, queued_at, updated_at, model, rating, confidence, scores_json, error FROM rating_jobs WHERE image_id=?",
                (image_id,),
            ).fetchone()
            if rating_row is not None:
                status_value = rating_row["status"]
                queued_value = rating_row["queued_at"]
                if status_value == "pending" and queued_value is not None:
                    pos_row = conn.execute(
                        "SELECT COUNT(*) FROM rating_jobs WHERE status='pending' AND queued_at <= ?",
                        (queued_value,),
                    ).fetchone()
                    if pos_row is not None:
                        rating_position = int(pos_row[0])
        finally:
            conn.close()

        metadata_json = row_get("metadata_json")
        metadata = json.loads(metadata_json) if metadata_json else {}
        characters = extract_character_details(metadata)
        positive_prompt = metadata.get("prompt") if isinstance(metadata, dict) else None
        if not positive_prompt and isinstance(metadata, dict):
            positive_prompt = (
                metadata.get("v4_prompt", {}).get("caption", {}).get("base_caption")
            )
        negative_prompt = metadata.get("uc") if isinstance(metadata, dict) else None
        if not negative_prompt and isinstance(metadata, dict):
            negative_prompt = (
                metadata.get("v4_negative_prompt", {})
                .get("caption", {})
                .get("base_caption")
            )

        image_path = row_get("path") or ""
        image_identifier = row_get("id", image_id) or image_id

        data = {
            "image": {
                "id": image_identifier,
                "name": row_get("name"),
                "path": image_path,
                "file_url": self.file_url_for(image_identifier, image_path),
                "thumb_url": self.thumb_url_for(image_identifier, image_path),
                "width": row_get("width"),
                "height": row_get("height"),
                "seed": row_get("seed"),
                "model": row_get("model") or row_get("source"),
                "description": row_get("description"),
                "metadata": metadata,
                "mtime": row_get("mtime"),
                "size": row_get("size"),
            },
            "tags": [
                {
                    "tag": tag,
                    "norm": norm,
                    "kind": kind,
                    "emphasis": emphasis,
                    "weight": weight,
                    "raw": raw,
                    "source": source or "embedded",
                    "count": counts.get((norm, kind), 1),
                }
                for tag, norm, kind, emphasis, weight, raw, source in tag_rows
            ],
            "characters": characters,
            "prompts": {
                "positive": positive_prompt or "",
                "negative": negative_prompt or "",
            },
        }
        rating_value = row_get("rating")
        rating_confidence = row_get("rating_confidence")
        rating_updated = row_get("rating_updated")
        rating_scores: Dict[str, float] = {}
        if rating_row is not None:
            raw_scores = rating_row["scores_json"]
            if raw_scores:
                try:
                    parsed_scores = json.loads(raw_scores)
                except json.JSONDecodeError:
                    parsed_scores = {}
                if isinstance(parsed_scores, dict):
                    rating_scores = {
                        str(k).lower(): float(v)
                        for k, v in parsed_scores.items()
                        if isinstance(v, (int, float))
                    }
        if not rating_scores:
            for tag_entry in tag_rows:
                tag_kind = tag_entry[2]
                raw_payload = tag_entry[5]
                if tag_kind != "rating" or not isinstance(raw_payload, str):
                    continue
                try:
                    payload = json.loads(raw_payload)
                except json.JSONDecodeError:
                    continue
                scores_payload = (
                    payload.get("scores") if isinstance(payload, dict) else None
                )
                if isinstance(scores_payload, dict):
                    rating_scores = {
                        str(k).lower(): float(v)
                        for k, v in scores_payload.items()
                        if isinstance(v, (int, float))
                    }
                    break
        if not rating_value and rating_scores:
            best_label, best_score = max(
                rating_scores.items(), key=lambda item: item[1]
            )
            rating_value = best_label
            rating_confidence = best_score
        data["rating"] = {
            "value": rating_value,
            "confidence": rating_confidence,
            "updated": rating_updated,
            "scores": rating_scores,
        }
        for character in data["characters"]:
            for tag in character.get("tags", []):
                tag_norm = tag.get("norm")
                kind = tag.get("kind", "character")
                tag["count"] = counts.get((tag_norm, kind), 1)

        clip_enabled = False
        auto_enabled = False
        config: Optional[LocalBooruConfig] = getattr(self.server, "config", None)  # type: ignore[attr-defined]
        if config:
            clip_enabled = bool(getattr(config, "clip_enabled", False))
            auto_enabled = bool(
                getattr(config, "auto_tag_background", False)
                or getattr(config, "auto_tag_missing", False)
            )
        rating_enabled = True

        clip_info: Dict[str, object] = {"enabled": clip_enabled}
        if clip_row is not None:
            clip_info.update(
                {
                    "status": str(clip_row["status"])
                    if clip_row["status"]
                    else "unknown",
                    "model": clip_row["model"],
                    "queued_at": clip_row["queued_at"],
                    "updated_at": clip_row["updated_at"],
                    "error": clip_row["error"],
                    "has_embedding": bool(clip_row["status"] == "ready"),
                }
            )
        else:
            clip_info.update(
                {
                    "status": "disabled" if not clip_enabled else "missing",
                    "model": getattr(config, "clip_model_name", None)
                    if config
                    else None,
                    "queued_at": None,
                    "updated_at": None,
                    "error": None,
                    "has_embedding": False,
                }
            )

        auto_has_tags = False
        for row in tag_rows:
            source_value = None
            try:
                source_value = row["source"]
            except (KeyError, TypeError):
                try:
                    source_value = row[-1]
                except (IndexError, TypeError):
                    source_value = None
            if (source_value or "embedded") == "auto":
                auto_has_tags = True
                break
        auto_info: Dict[str, object] = {
            "enabled": auto_enabled,
            "has_tags": auto_has_tags,
            "position": auto_position,
        }
        if auto_row is not None:
            auto_info.update(
                {
                    "status": str(auto_row["status"])
                    if auto_row["status"]
                    else "unknown",
                    "queued_at": auto_row["queued_at"],
                    "updated_at": auto_row["updated_at"],
                    "model": auto_row["model"],
                    "error": auto_row["error"],
                }
            )
        else:
            auto_info.update(
                {
                    "status": "disabled" if not auto_enabled else "missing",
                    "queued_at": None,
                    "updated_at": None,
                    "model": getattr(config, "auto_tag_model", None)
                    if config
                    else None,
                    "error": None,
                }
            )

        rating_has_value = bool(rating_value)
        rating_info: Dict[str, object] = {
            "enabled": rating_enabled,
            "has_rating": rating_has_value or bool(rating_row and rating_row["rating"]),
            "position": rating_position,
            "confidence": rating_confidence,
            "rating": rating_value,
        }
        if rating_scores:
            rating_info["scores"] = rating_scores
        if rating_row is not None:
            rating_info.update(
                {
                    "status": str(rating_row["status"])
                    if rating_row["status"]
                    else "unknown",
                    "queued_at": rating_row["queued_at"],
                    "updated_at": rating_row["updated_at"],
                    "model": rating_row["model"],
                    "confidence": rating_row["confidence"],
                    "error": rating_row["error"],
                    "rating": rating_row["rating"] or rating_value,
                }
            )
        else:
            rating_info.update(
                {
                    "status": "disabled" if not rating_enabled else "missing",
                    "queued_at": None,
                    "updated_at": rating_updated,
                    "model": getattr(config, "rating_model", None) if config else None,
                    "error": None,
                }
            )

        data["processing"] = {
            "clip": clip_info,
            "auto": auto_info,
            "rating": rating_info,
        }

        self._send_json(data)

    def _handle_clip_control(self, action: str) -> None:
        clip_indexer: Optional[ClipIndexer] = self.server.clip_indexer  # type: ignore[attr-defined]
        if clip_indexer is None:
            self.send_error(HTTPStatus.BAD_REQUEST, "CLIP indexing disabled")
            return
        if action == "pause":
            clip_indexer.pause()
        elif action == "resume":
            clip_indexer.resume()
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def _handle_auto_control(self, action: str) -> None:
        auto_indexer: Optional[AutoTagIndexer] = self.server.auto_indexer  # type: ignore[attr-defined]
        if auto_indexer is None:
            self.send_error(HTTPStatus.BAD_REQUEST, "Auto-tagging disabled")
            return
        if action == "pause":
            auto_indexer.pause()
        elif action == "resume":
            auto_indexer.resume()
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def _handle_clip_search(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing request body")
            return
        try:
            body = self.rfile.read(length)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.error("Failed to read request body: %s", exc)
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid body")
            return
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid JSON")
            return

        query = payload.get("query")
        positive = payload.get("positive") or []
        negative = payload.get("negative") or []
        positive_images = payload.get("positive_images") or []
        negative_images = payload.get("negative_images") or []
        tag_query = payload.get("tag_query") or ""
        limit = payload.get("limit") or 20
        offset = payload.get("offset") or 0
        include_tags = _coerce_bool(payload.get("include_tags", True), True)
        try:
            limit = max(1, min(int(limit), 200))
        except (ValueError, TypeError):
            limit = 20
        try:
            offset = max(0, int(offset))
        except (ValueError, TypeError):
            offset = 0

        positive_queries = []
        if isinstance(query, str) and query.strip():
            positive_queries.append(query.strip())
        if isinstance(positive, list):
            positive_queries.extend(
                str(item) for item in positive if isinstance(item, str) and item.strip()
            )
        negative_queries = []
        if isinstance(negative, list):
            negative_queries.extend(
                str(item) for item in negative if isinstance(item, str) and item.strip()
            )

        db: LocalBooruDatabase = self.server.db  # type: ignore[attr-defined]
        config: LocalBooruConfig = self.server.config  # type: ignore[attr-defined]

        positive_vectors: List[np.ndarray] = []
        positive_vector_payload = payload.get("positive_vector")
        if isinstance(positive_vector_payload, list):
            vector_strings = positive_vector_payload
        elif isinstance(positive_vector_payload, str):
            vector_strings = [positive_vector_payload]
        else:
            vector_strings = []
        for vector_str in vector_strings:
            if not isinstance(vector_str, str) or not vector_str:
                continue
            try:
                decoded = base64.b64decode(vector_str)
            except (binascii.Error, ValueError):  # type: ignore[name-defined]
                continue
            arr = np.frombuffer(decoded, dtype=np.float32)
            if arr.size == 0:
                continue
            norm = np.linalg.norm(arr)
            if not np.isfinite(norm) or norm == 0:
                continue
            positive_vectors.append(arr / norm)

        restrict_ids = None
        if isinstance(tag_query, str) and tag_query.strip():
            conn = db.new_connection()
            try:
                tokens = tokens_from_query(tag_query)
                restrict_ids = matched_image_ids(conn, tokens, config)
            finally:
                conn.close()

        full_results = perform_clip_search(
            db=db,
            config=config,
            positive_text=positive_queries,
            negative_text=negative_queries,
            positive_images=positive_images
            if isinstance(positive_images, list)
            else [],
            negative_images=negative_images
            if isinstance(negative_images, list)
            else [],
            limit=0,
            restrict_to_ids=restrict_ids,
            positive_vectors=positive_vectors or None,
        )

        total = len(full_results)
        window = (
            full_results[offset : offset + limit] if limit else full_results[offset:]
        )
        payload = self._build_clip_response(
            window,
            total,
            offset,
            limit,
            include_tags=include_tags,
        )
        self._send_json(payload)

    def _handle_clip_search_file(self) -> None:
        config: LocalBooruConfig = self.server.config  # type: ignore[attr-defined]
        if not getattr(config, "clip_enabled", False):
            self.send_error(HTTPStatus.BAD_REQUEST, "CLIP indexing disabled")
            return

        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            self.send_error(HTTPStatus.BAD_REQUEST, "Expected multipart form data")
            return

        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing request body")
            return
        try:
            body = self.rfile.read(length)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.error("Failed to read upload body: %s", exc)
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid body")
            return

        fields, files = self._parse_multipart_form(body, content_type)
        upload_info = None
        for file_entry in files:
            if file_entry.get("name") == "file":
                upload_info = file_entry
                break
        if upload_info is None and files:
            upload_info = files[0]
        if upload_info is None:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing file upload")
            return

        file_bytes = upload_info.get("data") or b""
        if not file_bytes:
            self.send_error(HTTPStatus.BAD_REQUEST, "Empty upload")
            return

        filename = upload_info.get("filename") or "upload"

        if Image is None:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Pillow not available")
            return
        try:
            image = Image.open(io.BytesIO(file_bytes))
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.error("Failed to parse uploaded image: %s", exc)
            self.send_error(HTTPStatus.BAD_REQUEST, "Unrecognised image data")
            return
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")
        else:
            image = image.convert("RGB")

        try:
            model = get_clip_model(config)
        except RuntimeError as exc:  # pragma: no cover - optional dependency missing
            LOGGER.error("Unable to load CLIP model: %s", exc)
            self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "CLIP model unavailable")
            return

        try:
            features = model.compute_image_features([image])
        except Exception as exc:  # pragma: no cover
            LOGGER.error("Failed to compute CLIP vector for upload: %s", exc)
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Failed to process image")
            return
        if getattr(features, "size", 0) == 0:
            self.send_error(
                HTTPStatus.INTERNAL_SERVER_ERROR, "CLIP feature extraction failed"
            )
            return
        vector = features[0]
        vector = vector.astype(np.float32)
        norm = np.linalg.norm(vector)
        if not np.isfinite(norm) or norm == 0:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Invalid CLIP vector")
            return
        vector /= norm
        vector_b64 = base64.b64encode(vector.tobytes()).decode("ascii")

        def _field(name: str, default: str = "") -> str:
            values = fields.get(name)
            if not values:
                return default
            return values[0]

        try:
            limit = max(1, min(int(_field("limit", "20")), 200))
        except ValueError:
            limit = 20
        try:
            offset = max(0, int(_field("offset", "0")))
        except ValueError:
            offset = 0
        tag_query = _field("tag_query", "") or ""
        include_tags = _coerce_bool(_field("include_tags", "0"), False)

        restrict_ids = None
        if isinstance(tag_query, str) and tag_query.strip():
            conn = self.server.db.new_connection()  # type: ignore[attr-defined]
            try:
                tokens = tokens_from_query(tag_query)
                restrict_ids = matched_image_ids(conn, tokens, config)
            finally:
                conn.close()

        db: LocalBooruDatabase = self.server.db  # type: ignore[attr-defined]
        full_results = perform_clip_search(
            db=db,
            config=config,
            positive_vectors=[vector],
            limit=0,
            restrict_to_ids=restrict_ids,
        )

        total = len(full_results)
        window = (
            full_results[offset : offset + limit] if limit else full_results[offset:]
        )
        payload = self._build_clip_response(
            window,
            total,
            offset,
            limit,
            include_tags=include_tags,
        )
        payload["vector"] = vector_b64
        payload["filename"] = filename
        self._send_json(payload)

    def _handle_image_tags(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing request body")
            return
        try:
            raw_body = self.rfile.read(length)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.error("Failed to read tag payload: %s", exc)
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid body")
            return
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid JSON")
            return
        ids_raw = payload.get("ids")
        if not isinstance(ids_raw, list):
            self.send_error(HTTPStatus.BAD_REQUEST, "ids must be a list")
            return
        image_ids: List[int] = []
        for value in ids_raw:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed < 0:
                continue
            image_ids.append(parsed)
        if not image_ids:
            self._send_json({"tags": {}})
            return

        db: LocalBooruDatabase = self.server.db  # type: ignore[attr-defined]
        conn = db.new_connection()
        try:
            tag_map = fetch_tags_for_images(conn, image_ids)
        finally:
            conn.close()

        serializable: Dict[str, List[Dict[str, object]]] = {
            str(image_id): tags for image_id, tags in tag_map.items()
        }
        for image_id in image_ids:
            key = str(image_id)
            if key not in serializable:
                serializable[key] = []

        self._send_json({"tags": serializable})

    def _lookup_image_path(self, image_id: int) -> Optional[str]:
        db: LocalBooruDatabase = self.server.db  # type: ignore[attr-defined]
        conn = db.new_connection()
        try:
            row = conn.execute(
                "SELECT path FROM images WHERE id=?", (image_id,)
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return row["path"]

    def _stream_path(
        self, path: Path, *, content_type: str, cache_control: str
    ) -> None:
        try:
            stat = path.stat()
            with path.open("rb") as fh:
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(stat.st_size))
                self.send_header("Cache-Control", cache_control)
                self.send_header(
                    "Last-Modified", formatdate(stat.st_mtime, usegmt=True)
                )
                self.end_headers()
                shutil.copyfileobj(fh, self.wfile)
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND, "File missing")
        except BrokenPipeError:  # pragma: no cover - client disconnected
            LOGGER.warning("Client disconnected while streaming %s", path)

    def _handle_file(self, identifier: str) -> None:
        try:
            image_id = int(identifier)
        except ValueError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid identifier")
            return
        stored_path = self._lookup_image_path(image_id)
        if not stored_path:
            self.send_error(HTTPStatus.NOT_FOUND, "Image not found")
            return
        resolved = self.server.resolve_path(stored_path)  # type: ignore[attr-defined]
        if resolved is None or not resolved.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "File missing")
            return
        content_type = (
            mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
        )
        self._stream_path(
            resolved,
            content_type=content_type,
            cache_control="public, max-age=31536000",
        )

    def _handle_thumbnail(self, identifier: str) -> None:
        try:
            image_id = int(identifier)
        except ValueError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid identifier")
            return
        stored_path = self._lookup_image_path(image_id)
        if not stored_path:
            self.send_error(HTTPStatus.NOT_FOUND, "Image not found")
            return
        resolved = self.server.resolve_path(stored_path)  # type: ignore[attr-defined]
        if resolved is None or not resolved.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "File missing")
            return
        thumb_path = self.server.ensure_thumbnail(resolved)  # type: ignore[attr-defined]
        if thumb_path and thumb_path.exists():
            self._stream_path(
                thumb_path,
                content_type="image/jpeg",
                cache_control="public, max-age=86400",
            )
            return
        fallback_type = (
            mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
        )
        self._stream_path(
            resolved,
            content_type=fallback_type,
            cache_control="public, max-age=31536000",
        )

    def log_message(
        self, format: str, *args
    ) -> None:  # pragma: no cover - adjust logging
        message = format % args
        low_traffic_paths = ("/api/status/", "/api/rating_counts", "/api/rating_status")
        if any(path in message for path in low_traffic_paths):
            LOGGER.debug("%s - %s", self.address_string(), message)
        else:
            LOGGER.info("%s - %s", self.address_string(), message)

    # --- helper serialization --------------------------------------------------------

    def _send_json(self, payload: Dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def file_url_for(self, image_id: int, path: str) -> str:
        digest = hashlib.sha1(path.encode("utf-8")).hexdigest()
        return f"/files/{image_id}?v={digest[:10]}"

    def thumb_url_for(self, image_id: int, path: str) -> str:
        digest = hashlib.sha1(path.encode("utf-8")).hexdigest()
        return f"/thumbs/{image_id}?v={digest[:10]}"


class LocalBooruHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        RequestHandlerClass=LocalBooruRequestHandler,
        config: Optional[LocalBooruConfig] = None,
        db: Optional[LocalBooruDatabase] = None,
        scanner: Optional[Scanner] = None,
        progress: Optional[ClipProgress] = None,
        clip_indexer: Optional[ClipIndexer] = None,
        auto_progress: Optional[AutoTagProgress] = None,
        auto_indexer: Optional[AutoTagIndexer] = None,
    ) -> None:
        super().__init__(server_address, RequestHandlerClass)
        self.config = config
        self.db = db
        self.scanner = scanner
        self.progress = progress
        self.clip_indexer = clip_indexer
        self.auto_progress = auto_progress
        self.auto_indexer = auto_indexer
        self._thumb_lock = threading.Lock()

        # Tag stats cache
        self._tag_stats_cache = []
        self._tag_stats_last_modified = 0.0
        self._tag_stats_lock = threading.RLock()
        self._tag_stats_thread = None
        self._shutdown_event = threading.Event()

        # Initialize tag stats cache before server starts
        LOGGER.info("Initializing tag stats cache...")
        self._refresh_tag_stats_cache()
        LOGGER.info(
            "Tag stats cache initialized with %d tags", len(self._tag_stats_cache)
        )
        self._start_tag_stats_refresh_thread()

        def _resolve_base(path: Path) -> Path:
            if path is None:
                return Path.cwd()
            try:
                return path.resolve(strict=False)
            except Exception:  # pragma: no cover - fallback
                return path.absolute()

        if config is not None:
            bases = [
                _resolve_base(config.root),
                *(_resolve_base(p) for p in config.extra_roots),
            ]
            # preserve order while removing duplicates
            self.allowed_roots = list(dict.fromkeys(bases))
            self.thumb_cache = _resolve_base(config.thumb_cache)
            self.thumb_cache.mkdir(parents=True, exist_ok=True)
            self.thumb_size = config.thumb_size
            self.pillow_available = bool(config.enable_thumbs and Image is not None)
        else:  # pragma: no cover - defensive
            base = Path.cwd()
            self.allowed_roots = [base]
            self.thumb_cache = base
            self.thumb_size = 512
            self.pillow_available = False

    def _is_within_allowed(self, path: Path) -> bool:
        resolved = path.resolve(strict=False)
        for base in self.allowed_roots:
            try:
                resolved.relative_to(base)
                return True
            except ValueError:
                continue
        return False

    def resolve_path(self, stored_path: str) -> Optional[Path]:
        candidate = Path(stored_path)
        search_paths = []
        if candidate.is_absolute():
            search_paths.append(candidate)
        else:
            if self.config is not None:
                search_paths.append(self.config.root / candidate)
                for extra in self.allowed_roots[1:]:
                    search_paths.append(extra / candidate)
        for option in search_paths:
            resolved = option.resolve(strict=False)
            if self._is_within_allowed(resolved):
                return resolved
        return None

    def thumbnail_cache_key(self, source: Path) -> str:
        resolved = source.resolve(strict=False)
        return hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()

    def ensure_thumbnail(self, source: Path) -> Optional[Path]:
        if not self.pillow_available or Image is None:
            return None
        try:
            source_stat = source.stat()
        except FileNotFoundError:
            return None
        cache_key = self.thumbnail_cache_key(source)
        dest = self.thumb_cache / f"{cache_key}.jpg"
        if dest.exists() and dest.stat().st_mtime >= source_stat.st_mtime:
            return dest
        with self._thumb_lock:
            if dest.exists() and dest.stat().st_mtime >= source_stat.st_mtime:
                return dest
            try:
                with Image.open(source) as img:
                    img = img.convert("RGB")
                    resample = getattr(Image, "Resampling", None)
                    if resample and hasattr(resample, "LANCZOS"):
                        method = resample.LANCZOS
                    else:
                        method = getattr(
                            Image, "LANCZOS", getattr(Image, "ANTIALIAS", Image.BICUBIC)
                        )
                    img.thumbnail((self.thumb_size, self.thumb_size), method)
                    temp = dest.with_suffix(".tmp.jpg")
                    img.save(temp, format="JPEG", quality=88, optimize=True)
                    temp.replace(dest)
                    os.utime(
                        dest,
                        (source_stat.st_mtime, source_stat.st_mtime),
                        follow_symlinks=False,
                    )
            except Exception:  # pragma: no cover - thumbnail generation best-effort
                LOGGER.exception("Failed to create thumbnail for %s", source)
                return None
        return dest

    def _refresh_tag_stats_cache(self) -> None:
        """Refresh the in-memory tag stats cache from the database."""
        if not self.db:
            return

        try:
            tag_stats, last_modified = self.db.get_complete_tag_stats()
            with self._tag_stats_lock:
                old_count = len(self._tag_stats_cache)
                self._tag_stats_cache = tag_stats
                self._tag_stats_last_modified = last_modified
                LOGGER.debug(
                    "Tag stats cache refreshed: %d tags (was %d), last_modified=%s",
                    len(tag_stats),
                    old_count,
                    time.ctime(last_modified),
                )
        except Exception as e:
            LOGGER.error("Failed to refresh tag stats cache: %s", e)

    def _start_tag_stats_refresh_thread(self) -> None:
        """Start the background thread that periodically refreshes tag stats."""

        def refresh_loop():
            LOGGER.info("Tag stats refresh thread started (20 second interval)")
            while not self._shutdown_event.is_set():
                # Wait for 20 seconds or until shutdown
                if self._shutdown_event.wait(20.0):
                    break
                self._refresh_tag_stats_cache()
            LOGGER.info("Tag stats refresh thread stopped")

        self._tag_stats_thread = threading.Thread(target=refresh_loop, daemon=True)
        self._tag_stats_thread.start()

    def get_cached_tag_stats(self) -> Tuple[List[Dict[str, object]], float]:
        """Get tag stats from the in-memory cache."""
        with self._tag_stats_lock:
            return self._tag_stats_cache.copy(), self._tag_stats_last_modified

    def shutdown(self) -> None:
        """Shutdown the server and background threads."""
        self._shutdown_event.set()
        if self._tag_stats_thread and self._tag_stats_thread.is_alive():
            self._tag_stats_thread.join(timeout=1.0)
        super().shutdown()

    def refresh_tag_stats_cache(self) -> None:
        """Trigger an immediate refresh of the tag stats cache.

        Call this when tags have been modified (e.g., after image imports,
        auto-tagging, or manual tag changes).
        """
        LOGGER.info("Tag stats cache refresh triggered manually")
        self._refresh_tag_stats_cache()


def run_server(
    config: LocalBooruConfig,
    db: LocalBooruDatabase,
    scanner: Scanner,
    progress: ClipProgress,
    clip_indexer: Optional[ClipIndexer],
) -> None:  # pragma: no cover - networking
    httpd = create_http_server(
        config=config,
        db=db,
        scanner=scanner,
        progress=progress,
        clip_indexer=clip_indexer,
        auto_progress=None,
        auto_indexer=None,
    )
    LOGGER.info(
        "HTTP server ready, starting to listen on http://%s:%d",
        config.host,
        config.port,
    )
    try:
        httpd.serve_forever()
    finally:
        httpd.shutdown()
        httpd.server_close()


def create_http_server(
    config: LocalBooruConfig,
    db: LocalBooruDatabase,
    scanner: Scanner,
    progress: ClipProgress,
    clip_indexer: Optional[ClipIndexer] = None,
    auto_progress: Optional[AutoTagProgress] = None,
    auto_indexer: Optional[AutoTagIndexer] = None,
) -> LocalBooruHTTPServer:
    return LocalBooruHTTPServer(
        (config.host, config.port),
        config=config,
        db=db,
        scanner=scanner,
        progress=progress,
        clip_indexer=clip_indexer,
        auto_progress=auto_progress,
        auto_indexer=auto_indexer,
    )
