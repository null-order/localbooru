"""HTTP server for localbooru."""
from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import os
import shutil
import threading
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional

from email.utils import formatdate

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

try:  # Pillow optional for thumbnails
    from PIL import Image
except ImportError:  # pragma: no cover - optional dependency
    Image = None  # type: ignore


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
        if parsed.path == "/api/search/clip":
            self._handle_clip_search()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def _handle_clip_status(self) -> None:
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
        positive_images = payload.get("positive_images") or []
        negative_images = payload.get("negative_images") or []
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
            positive_text=positive_queries,
            negative_text=negative_queries,
            positive_images=positive_images if isinstance(positive_images, list) else [],
            negative_images=negative_images if isinstance(negative_images, list) else [],
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

    def _lookup_image_path(self, image_id: int) -> Optional[str]:
        db: LocalBooruDatabase = self.server.db  # type: ignore[attr-defined]
        conn = db.new_connection()
        try:
            row = conn.execute("SELECT path FROM images WHERE id=?", (image_id,)).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return row["path"]

    def _stream_path(self, path: Path, *, content_type: str, cache_control: str) -> None:
        try:
            stat = path.stat()
            with path.open('rb') as fh:
                self.send_response(HTTPStatus.OK)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(stat.st_size))
                self.send_header('Cache-Control', cache_control)
                self.send_header('Last-Modified', formatdate(stat.st_mtime, usegmt=True))
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
        content_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
        self._stream_path(resolved, content_type=content_type, cache_control="public, max-age=31536000")

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
            self._stream_path(thumb_path, content_type="image/jpeg", cache_control="public, max-age=86400")
            return
        fallback_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
        self._stream_path(resolved, content_type=fallback_type, cache_control="public, max-age=31536000")

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
        self._thumb_lock = threading.Lock()

        def _resolve_base(path: Path) -> Path:
            if path is None:
                return Path.cwd()
            try:
                return path.resolve(strict=False)
            except Exception:  # pragma: no cover - fallback
                return path.absolute()

        if config is not None:
            bases = [_resolve_base(config.root), *(_resolve_base(p) for p in config.extra_roots)]
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
        return hashlib.sha1(str(resolved).encode('utf-8')).hexdigest()

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
                    img = img.convert('RGB')
                    resample = getattr(Image, 'Resampling', None)
                    if resample and hasattr(resample, 'LANCZOS'):
                        method = resample.LANCZOS
                    else:
                        method = getattr(Image, 'LANCZOS', getattr(Image, 'ANTIALIAS', Image.BICUBIC))
                    img.thumbnail((self.thumb_size, self.thumb_size), method)
                    temp = dest.with_suffix('.tmp.jpg')
                    img.save(temp, format='JPEG', quality=88, optimize=True)
                    temp.replace(dest)
                    os.utime(dest, (source_stat.st_mtime, source_stat.st_mtime), follow_symlinks=False)
            except Exception:  # pragma: no cover - thumbnail generation best-effort
                LOGGER.exception("Failed to create thumbnail for %s", source)
                return None
        return dest


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
