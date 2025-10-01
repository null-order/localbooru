"""Tag-based search helpers for LocalBooru."""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Dict, List, Sequence, Tuple

from .tags import normalize_tag, parse_query_tokens

QueryToken = Tuple[str, str, bool]


def tokens_from_query(query: str) -> List[QueryToken]:
    return parse_query_tokens(query)


def build_matched_cte(tokens: Sequence[QueryToken]) -> Tuple[str, List[str]]:
    positives = [t for t in tokens if not t[2]]
    negatives = [t for t in tokens if t[2]]

    positive_clauses: List[str] = []
    positive_params: List[str] = []
    for norm, kind, _ in positives:
        match = f"norm:{norm}"
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
        match = f"norm:{norm}"
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
) -> Tuple[List[sqlite3.Row], int]:
    cte, params = build_matched_cte(tokens)
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
) -> List[Dict[str, object]]:
    cte, params = build_matched_cte(tokens)
    sql = (
        f"{cte} "
        "SELECT t.tag, t.norm, t.kind, COUNT(*) AS freq "
        "FROM matched m JOIN tags t ON t.image_id = m.image_id "
        "GROUP BY t.norm, t.kind "
        "ORDER BY CASE t.kind WHEN 'prompt' THEN 0 WHEN 'character' THEN 0 WHEN 'description' THEN 0 WHEN 'negative' THEN 1 ELSE 2 END, freq DESC, t.tag ASC LIMIT ?"
    )
    rows = conn.execute(sql, (*params, limit)).fetchall()
    return [
        {"tag": row[0], "norm": row[1], "kind": row[2], "freq": row[3]}
        for row in rows
    ]


def matched_image_ids(conn: sqlite3.Connection, tokens: Sequence[QueryToken]) -> List[int]:
    if not tokens:
        rows = conn.execute("SELECT id FROM images").fetchall()
        return [row[0] for row in rows]
    cte, params = build_matched_cte(tokens)
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
        if kind_filter in ("prompt", "negative", "character", "description"):
            sql += " WHERE kind = ?"
            params.append(kind_filter)
        sql += " GROUP BY norm, kind ORDER BY freq DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, tuple(params)).fetchall()
    else:
        norm = normalize_tag(prefix)
        match = f"norm:{norm}*"
        params: List[object] = [match]
        sql = (
            "SELECT tag, norm, kind, COUNT(DISTINCT image_id) AS freq "
            "FROM tag_index WHERE tag_index MATCH ?"
        )
        if kind_filter in ("prompt", "negative", "character", "description"):
            sql += " AND kind = ?"
            params.append(kind_filter)
        sql += " GROUP BY norm, kind ORDER BY freq DESC"
        rows = conn.execute(sql, tuple(params)).fetchall()
        seen = {(row[1], row[2]) for row in rows}
        results = list(rows)
        like_pattern = f"%{norm}%"
        if norm and len(norm) >= 2:
            like_sql = (
                "SELECT tag, norm, kind, COUNT(DISTINCT image_id) AS freq FROM tags WHERE norm LIKE ?"
            )
            like_params: List[object] = [like_pattern]
            if kind_filter in ("prompt", "negative", "character", "description"):
                like_sql += " AND kind = ?"
                like_params.append(kind_filter)
            like_sql += " GROUP BY norm, kind ORDER BY freq DESC LIMIT ?"
            like_params.append(limit * 2)
            for row in conn.execute(like_sql, tuple(like_params)):
                key = (row[1], row[2])
                if key not in seen:
                    results.append(row)
                    seen.add(key)
        rows = results[:limit]
    return [
        {"tag": row[0], "norm": row[1], "kind": row[2], "freq": row[3]}
        for row in rows
    ]


def fetch_tags_for_images(
    conn: sqlite3.Connection,
    image_ids: Sequence[int],
) -> Dict[int, List[Dict[str, object]]]:
    if not image_ids:
        return {}
    placeholders = ",".join("?" for _ in image_ids)
    rows = conn.execute(
        f"SELECT image_id, tag, norm, kind FROM tags WHERE image_id IN ({placeholders})",
        tuple(image_ids),
    ).fetchall()
    grouped: Dict[int, List[Dict[str, object]]] = defaultdict(list)
    for image_id, tag, norm, kind in rows:
        if kind not in ("prompt", "character", "negative"):
            continue
        grouped[image_id].append({"tag": tag, "norm": norm, "kind": kind})
    return {image_id: tags for image_id, tags in grouped.items()}
