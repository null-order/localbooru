"""Tag-based search helpers for LocalBooru."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple

if TYPE_CHECKING:
    from .config import LocalBooruConfig

from .tags import normalize_tag, parse_query_tokens

QueryToken = Tuple[str, str, bool]


def normalize_path_pattern(pattern: str, config: Optional["LocalBooruConfig"]) -> str:
    """Normalize a path pattern based on configured roots.

    If the pattern starts with the main root, convert to relative.
    If it starts with an extra root, keep as absolute.
    Auto-adds wildcards for better UX if no wildcards are present.
    """
    if not config:
        pattern = pattern.strip()
    else:
        pattern = pattern.strip()

        # Check main root first
        main_root_str = str(config.root).rstrip("/") + "/"
        if pattern.startswith(main_root_str):
            relative = pattern[len(main_root_str) :].lstrip("/")
            pattern = relative

        # Check extra roots
        else:
            for extra_root in config.extra_roots:
                extra_root_str = str(extra_root).rstrip("/") + "/"
                if pattern.startswith(extra_root_str):
                    break  # Keep absolute pattern as-is

    # Auto-add wildcards for better user experience
    if pattern and "*" not in pattern and "?" not in pattern:
        # If pattern ends with /, treat as directory search
        if pattern.endswith("/"):
            pattern = f"*/{pattern.rstrip('/')}/*"
        else:
            # Otherwise treat as substring search
            pattern = f"*{pattern}*"

    return pattern


def tokens_from_query(query: str) -> List[QueryToken]:
    return parse_query_tokens(query)


def _fts_quote(term: str) -> str:
    return '"' + term.replace('"', '""') + '"'


def build_matched_cte(
    tokens: Sequence[QueryToken], config: Optional["LocalBooruConfig"] = None
) -> Tuple[str, List[str]]:
    positives = [t for t in tokens if not t[2]]
    negatives = [t for t in tokens if t[2]]

    positive_clauses: List[str] = []
    positive_params: List[str] = []
    for norm, kind, _ in positives:
        if kind == "path":
            # Handle path searches with GLOB pattern matching
            normalized_pattern = normalize_path_pattern(norm, config)
            positive_clauses.append(
                "SELECT DISTINCT CAST(id AS INTEGER) FROM images WHERE path GLOB ?"
            )
            positive_params.append(normalized_pattern)
        elif kind in ("generator", "model", "sampler", "scheduler", "seed"):
            # Handle metadata field searches in images table
            positive_clauses.append(
                f"SELECT DISTINCT CAST(id AS INTEGER) FROM images WHERE {kind} LIKE ?"
            )
            positive_params.append(f"%{norm}%")
        elif kind in ("steps", "cfg_scale"):
            # Handle numeric metadata field searches
            # First try to parse as float, handling normalized decimals
            original_norm = norm.replace("_", ".")  # Convert normalized decimals back
            try:
                numeric_value = float(original_norm)
                positive_clauses.append(
                    f"SELECT DISTINCT CAST(id AS INTEGER) FROM images WHERE {kind} = ?"
                )
                positive_params.append(numeric_value)
            except ValueError:
                # If not numeric, treat as text search
                positive_clauses.append(
                    f"SELECT DISTINCT CAST(id AS INTEGER) FROM images WHERE CAST({kind} AS TEXT) LIKE ?"
                )
                positive_params.append(f"%{original_norm}%")
        else:
            match = f"norm:{_fts_quote(norm)}"
            if kind == "any":
                positive_clauses.append(
                    "SELECT DISTINCT CAST(image_id AS INTEGER) FROM tag_index WHERE kind IN ('prompt','character') AND tag_index MATCH ?"
                )
                positive_params.append(match)
            else:
                positive_clauses.append(
                    "SELECT DISTINCT CAST(image_id AS INTEGER) FROM tag_index WHERE kind=? AND tag_index MATCH ?"
                )
                positive_params.extend([kind, match])

    negative_clauses: List[str] = []
    negative_params: List[str] = []
    for norm, kind, _ in negatives:
        if kind == "path":
            # Handle negative path searches
            normalized_pattern = normalize_path_pattern(norm, config)
            negative_clauses.append(
                "SELECT DISTINCT CAST(id AS INTEGER) FROM images WHERE path GLOB ?"
            )
            negative_params.append(normalized_pattern)
        elif kind in ("generator", "model", "sampler", "scheduler", "seed"):
            # Handle negative metadata field searches in images table
            negative_clauses.append(
                f"SELECT DISTINCT CAST(id AS INTEGER) FROM images WHERE {kind} LIKE ?"
            )
            negative_params.append(f"%{norm}%")
        elif kind in ("steps", "cfg_scale"):
            # Handle negative numeric metadata field searches
            # First try to parse as float, handling normalized decimals
            original_norm = norm.replace("_", ".")  # Convert normalized decimals back
            try:
                numeric_value = float(original_norm)
                negative_clauses.append(
                    f"SELECT DISTINCT CAST(id AS INTEGER) FROM images WHERE {kind} = ?"
                )
                negative_params.append(numeric_value)
            except ValueError:
                # If not numeric, treat as text search
                negative_clauses.append(
                    f"SELECT DISTINCT CAST(id AS INTEGER) FROM images WHERE CAST({kind} AS TEXT) LIKE ?"
                )
                negative_params.append(f"%{original_norm}%")
        else:
            match = f"norm:{_fts_quote(norm)}"
            if kind == "any":
                negative_clauses.append(
                    "SELECT DISTINCT CAST(image_id AS INTEGER) FROM tag_index WHERE kind IN ('prompt','character') AND tag_index MATCH ?"
                )
                negative_params.append(match)
            else:
                negative_clauses.append(
                    "SELECT DISTINCT CAST(image_id AS INTEGER) FROM tag_index WHERE kind=? AND tag_index MATCH ?"
                )
                negative_params.extend([kind, match])

    filters: List[str] = []
    params: List[str] = []
    if positive_clauses:
        filters.append(f"id IN ({' INTERSECT '.join(positive_clauses)})")
        params.extend(positive_params)
    if negative_clauses:
        filters.append(f"id NOT IN ({' UNION '.join(negative_clauses)})")
        params.extend(negative_params)

    where_clause = ""
    if filters:
        where_clause = " WHERE " + " AND ".join(filters)
    cte = f"WITH matched AS (SELECT id AS image_id FROM images{where_clause})"
    return cte, params


def search_images(
    conn: sqlite3.Connection,
    tokens: Sequence[QueryToken],
    limit: int,
    offset: int,
    config: Optional["LocalBooruConfig"] = None,
) -> Tuple[List[sqlite3.Row], int]:
    cte, params = build_matched_cte(tokens, config)
    count_sql = f"{cte} SELECT COUNT(*) FROM matched"
    total_rows = conn.execute(count_sql, params).fetchone()[0]
    data_sql = (
        f"{cte} "
        "SELECT i.* FROM matched m "
        "JOIN images i ON i.id = m.image_id "
        "ORDER BY i.mtime DESC, i.id DESC LIMIT ? OFFSET ?"
    )
    rows = conn.execute(data_sql, (*params, limit, offset)).fetchall()
    return rows, total_rows


def collect_tag_facets(
    conn: sqlite3.Connection,
    tokens: Sequence[QueryToken],
    limit: int = 100,
    config: Optional["LocalBooruConfig"] = None,
) -> List[Dict[str, object]]:
    cte, params = build_matched_cte(tokens, config)
    sql = (
        f"{cte} "
        "SELECT t.tag, t.norm, t.kind, COUNT(*) AS freq "
        "FROM matched m JOIN tags t ON t.image_id = m.image_id "
        "GROUP BY t.norm, t.kind "
        "ORDER BY CASE t.kind WHEN 'prompt' THEN 0 WHEN 'rating' THEN 0 WHEN 'character' THEN 0 WHEN 'description' THEN 0 WHEN 'negative' THEN 1 ELSE 2 END, freq DESC, t.tag ASC LIMIT ?"
    )
    rows = conn.execute(sql, (*params, limit)).fetchall()
    return [
        {"tag": row[0], "norm": row[1], "kind": row[2], "freq": row[3]} for row in rows
    ]


def matched_image_ids(
    conn: sqlite3.Connection,
    tokens: Sequence[QueryToken],
    config: Optional["LocalBooruConfig"] = None,
) -> List[int]:
    if not tokens:
        rows = conn.execute("SELECT id FROM images").fetchall()
        return [row[0] for row in rows]
    cte, params = build_matched_cte(tokens, config)
    sql = f"{cte} SELECT image_id FROM matched"
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [row[0] for row in rows]


def autocomplete_tags(
    conn: sqlite3.Connection,
    prefix: str,
    kind_filter: str | None,
    limit: int = 20,
) -> List[Dict[str, object]]:
    if not prefix:
        sql = "SELECT tag, norm, kind, COUNT(DISTINCT image_id) AS freq FROM tags"
        params: List[object] = []
        if kind_filter in ("prompt", "negative", "character", "description", "rating"):
            sql += " WHERE kind = ?"
            params.append(kind_filter)
        sql += " GROUP BY norm, kind ORDER BY freq DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, tuple(params)).fetchall()
    else:
        # Parse search prefixes to extract the actual search term
        lowered = prefix.lower()
        search_term = prefix
        extracted_kind_filter = kind_filter

        # Check for search prefixes and extract the search term
        if lowered.startswith("path:") or lowered.startswith("in:"):
            # For path searches, don't return tag suggestions since they're not applicable
            return []
        elif lowered.startswith("char:"):
            search_term = prefix[5:].strip()
            extracted_kind_filter = "character"
        elif lowered.startswith("character:"):
            search_term = prefix[10:].strip()
            extracted_kind_filter = "character"
        elif lowered.startswith("prompt:"):
            search_term = prefix[7:].strip()
            extracted_kind_filter = "prompt"
        elif lowered.startswith("uc:"):
            search_term = prefix[3:].strip()
            extracted_kind_filter = "negative"
        elif lowered.startswith("rating:"):
            search_term = prefix[7:].strip()
            extracted_kind_filter = "rating"
        elif lowered in ("path", "in", "prompt", "char", "character", "uc", "rating"):
            # Just the prefix without colon - don't return suggestions
            return []

        # If we extracted an empty search term, don't proceed
        if not search_term:
            return []

        norm = normalize_tag(search_term)
        # Skip if normalization results in empty string or contains problematic characters
        if not norm:
            return []

        try:
            match = f"norm:{norm}*"
            params: List[object] = [match]
            sql = (
                "SELECT tag, norm, kind, COUNT(DISTINCT image_id) AS freq "
                "FROM tag_index WHERE tag_index MATCH ?"
            )
            if extracted_kind_filter in (
                "prompt",
                "negative",
                "character",
                "description",
                "rating",
            ):
                sql += " AND kind = ?"
                params.append(extracted_kind_filter)
            sql += " GROUP BY norm, kind ORDER BY freq DESC"
            rows = conn.execute(sql, tuple(params)).fetchall()
            seen = {(row[1], row[2]) for row in rows}
            results = list(rows)
        except sqlite3.OperationalError:
            # If FTS5 fails (e.g., due to syntax issues), fall back to empty results for FTS
            rows = []
            seen = set()
            results = []

        like_pattern = f"%{norm}%"
        if norm and len(norm) >= 2:
            like_sql = "SELECT tag, norm, kind, COUNT(DISTINCT image_id) AS freq FROM tags WHERE norm LIKE ?"
            like_params: List[object] = [like_pattern]
            if extracted_kind_filter in (
                "prompt",
                "negative",
                "character",
                "description",
                "rating",
            ):
                like_sql += " AND kind = ?"
                like_params.append(extracted_kind_filter)
            like_sql += " GROUP BY norm, kind ORDER BY freq DESC LIMIT ?"
            like_params.append(limit * 2)
            for row in conn.execute(like_sql, tuple(like_params)):
                key = (row[1], row[2])
                if key not in seen:
                    results.append(row)
                    seen.add(key)
        rows = results[:limit]
    return [
        {"tag": row[0], "norm": row[1], "kind": row[2], "freq": row[3]} for row in rows
    ]


def fetch_tags_for_images(
    conn: sqlite3.Connection,
    image_ids: Sequence[int],
) -> Dict[int, List[Dict[str, object]]]:
    if not image_ids:
        return {}
    placeholders = ",".join("?" for _ in image_ids)
    rows = conn.execute(
        f"SELECT image_id, tag, norm, kind, source FROM tags WHERE image_id IN ({placeholders})",
        tuple(image_ids),
    ).fetchall()
    grouped: Dict[int, List[Dict[str, object]]] = defaultdict(list)
    for image_id, tag, norm, kind, source in rows:
        if kind not in ("prompt", "character", "negative", "rating"):
            continue
        grouped[image_id].append(
            {
                "tag": tag,
                "norm": norm,
                "kind": kind,
                "source": source or "embedded",
            }
        )
    return {image_id: tags for image_id, tags in grouped.items()}
