"""HTTP server for localbooru."""
from __future__ import annotations

import json
import logging
import threading
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional

from .clip import ClipIndexer, ClipProgress
from .clip_search import perform_clip_search
from .config import LocalBooruConfig
from .database import LocalBooruDatabase
from .scanner import Scanner
from .metadata import extract_character_details
from .search import (
    autocomplete_tags,
    collect_tag_facets,
    fetch_tags_for_images,
    matched_image_ids,
    search_images,
    tokens_from_query,
)

LOGGER = logging.getLogger(__name__)


class LocalBooruRequestHandler(BaseHTTPRequestHandler):
    server_version = "LocalBooru/0.1"

    def do_GET(self) -> None:  # pragma: no cover - network path
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/":
            self._serve_index()
            return
        if path == "/api/status/clip":
            self._handle_clip_status()
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
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:  # pragma: no cover - network path
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/clip/pause":
            self._handle_clip_control("pause")
            return
        if parsed.path == "/api/clip/resume":
            self._handle_clip_control("resume")
            return
        if parsed.path == "/api/search/clip":
            self._handle_clip_search()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def _handle_clip_status(self) -> None:
        progress: ClipProgress = self.server.progress  # type: ignore[attr-defined]
        payload = progress.snapshot(self.server.db)  # type: ignore[attr-defined]
        blob = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

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
        conn = db.new_connection()
        try:
            tokens = tokens_from_query(query)
            rows, total = search_images(conn, tokens, limit, offset)
            facets = collect_tag_facets(conn, tokens)
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
                "tags": tag_map.get(row["id"], []),
            }
            for row in rows
        ]
        payload = {"images": images, "total": total, "facets": facets}
        self._send_json(payload)

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
        try:
            row = conn.execute("SELECT * FROM images WHERE id=?", (image_id,)).fetchone()
            if not row:
                self.send_error(HTTPStatus.NOT_FOUND, "Image not found")
                return
            tag_rows = conn.execute(
                "SELECT tag, norm, kind, emphasis, weight, raw FROM tags WHERE image_id=? ORDER BY kind, tag",
                (image_id,),
            ).fetchall()
            pairs = [(r[1], r[2]) for r in tag_rows]
            seen_pairs = []
            seen_set = set()
            for pair in pairs:
                if pair not in seen_set:
                    seen_set.add(pair)
                    seen_pairs.append(pair)
            counts: Dict[tuple[str, str], int] = {}
            if seen_pairs:
                selects = " UNION ALL ".join(["SELECT ? AS norm, ? AS kind"] * len(seen_pairs))
                params = [value for pair in seen_pairs for value in pair]
                sql_counts = (
                    "SELECT t.norm, t.kind, COUNT(DISTINCT t.image_id) FROM tags t "
                    f"JOIN ({selects}) wanted ON t.norm = wanted.norm AND t.kind = wanted.kind "
                    "GROUP BY t.norm, t.kind"
                )
                for norm, kind, freq in conn.execute(sql_counts, params):
                    counts[(norm, kind)] = freq
        finally:
            conn.close()

        metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        characters = extract_character_details(metadata)
        positive_prompt = metadata.get("prompt") if isinstance(metadata, dict) else None
        if not positive_prompt and isinstance(metadata, dict):
            positive_prompt = (
                metadata.get("v4_prompt", {})
                .get("caption", {})
                .get("base_caption")
            )
        negative_prompt = metadata.get("uc") if isinstance(metadata, dict) else None
        if not negative_prompt and isinstance(metadata, dict):
            negative_prompt = (
                metadata.get("v4_negative_prompt", {})
                .get("caption", {})
                .get("base_caption")
            )

        data = {
            "image": {
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
                "metadata": metadata,
                "mtime": row["mtime"],
                "size": row["size"],
            },
            "tags": [
                {
                    "tag": tag,
                    "norm": norm,
                    "kind": kind,
                    "emphasis": emphasis,
                    "weight": weight,
                    "raw": raw,
                    "count": counts.get((norm, kind), 1),
                }
                for tag, norm, kind, emphasis, weight, raw in tag_rows
            ],
            "characters": characters,
            "prompts": {
                "positive": positive_prompt or "",
                "negative": negative_prompt or "",
            },
        }
        for character in data["characters"]:
            for tag in character.get("tags", []):
                tag_norm = tag.get("norm")
                kind = tag.get("kind", "character")
                tag["count"] = counts.get((tag_norm, kind), 1)

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
        tag_query = payload.get("tag_query") or ""
        limit = payload.get("limit") or 20
        try:
            limit = max(1, min(int(limit), 200))
        except (ValueError, TypeError):
            limit = 20

        positive_queries = []
        if isinstance(query, str) and query.strip():
            positive_queries.append(query.strip())
        if isinstance(positive, list):
            positive_queries.extend(str(item) for item in positive if isinstance(item, str) and item.strip())
        negative_queries = []
        if isinstance(negative, list):
            negative_queries.extend(str(item) for item in negative if isinstance(item, str) and item.strip())

        db: LocalBooruDatabase = self.server.db  # type: ignore[attr-defined]
        config: LocalBooruConfig = self.server.config  # type: ignore[attr-defined]

        restrict_ids = None
        if isinstance(tag_query, str) and tag_query.strip():
            conn = db.new_connection()
            try:
                tokens = tokens_from_query(tag_query)
                restrict_ids = matched_image_ids(conn, tokens)
            finally:
                conn.close()

        results = perform_clip_search(
            db=db,
            config=config,
            positive=positive_queries,
            negative=negative_queries,
            limit=limit,
            restrict_to_ids=restrict_ids,
        )

        if not results:
            self._send_json({"results": [], "total": 0})
            return

        image_ids = [image_id for image_id, _score in results]
        conn = db.new_connection()
        try:
            placeholders = ",".join("?" for _ in image_ids)
            sql = f"SELECT * FROM images WHERE id IN ({placeholders})"
            rows = conn.execute(sql, tuple(image_ids)).fetchall()
            tag_map = fetch_tags_for_images(conn, image_ids)
        finally:
            conn.close()

        row_map = {row["id"]: row for row in rows}
        payload_results = []
        for image_id, score in results:
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
                    "tags": tag_map.get(row["id"], []),
                }
            )

        self._send_json({"results": payload_results, "total": len(payload_results)})

    def log_message(self, format: str, *args) -> None:  # pragma: no cover - adjust logging
        LOGGER.info("%s - %s", self.address_string(), format % args)

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
        return f"/files/{image_id}"

    def thumb_url_for(self, image_id: int, path: str) -> str:
        return f"/thumbs/{image_id}"


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
    ) -> None:
        super().__init__(server_address, RequestHandlerClass)
        self.config = config
        self.db = db
        self.scanner = scanner
        self.progress = progress
        self.clip_indexer = clip_indexer


def run_server(
    config: LocalBooruConfig,
    db: LocalBooruDatabase,
    scanner: Scanner,
    progress: ClipProgress,
    clip_indexer: Optional[ClipIndexer],
) -> None:  # pragma: no cover - networking
    LOGGER.info("HTTP server listening on http://%s:%d", config.host, config.port)
    httpd = LocalBooruHTTPServer(
        (config.host, config.port),
        config=config,
        db=db,
        scanner=scanner,
        progress=progress,
        clip_indexer=clip_indexer,
    )
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
