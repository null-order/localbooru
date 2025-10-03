"""Tag parsing utilities for LocalBooru."""
from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclasses.dataclass
class TagRecord:
    tag: str
    norm: str
    kind: str
    emphasis: str
    weight: float
    raw: str


_tag_normalize_regexes = [
    (re.compile(r"\s+"), "_"),
    (re.compile(r"[^a-z0-9_:-]"), "_"),
    (re.compile(r"_+"), "_"),
]


def normalize_tag(tag: str) -> str:
    value = tag.strip().lower()
    for pattern, repl in _tag_normalize_regexes:
        value = pattern.sub(repl, value)
    return value.strip("_")


def split_prompt(text: str) -> List[str]:
    tokens: List[str] = []
    buf: List[str] = []
    brace_level = 0
    bracket_level = 0
    for ch in text:
        if ch == "," and brace_level == 0 and bracket_level == 0:
            token = "".join(buf).strip()
            if token:
                tokens.append(token)
            buf = []
            continue
        if ch == "{":
            brace_level += 1
        elif ch == "}" and brace_level > 0:
            brace_level -= 1
        elif ch == "[":
            bracket_level += 1
        elif ch == "]" and bracket_level > 0:
            bracket_level -= 1
        buf.append(ch)
    if buf:
        token = "".join(buf).strip()
        if token:
            tokens.append(token)
    return tokens


def _strip_balanced_wrappers(token: str) -> Tuple[str, int, int]:
    strong = 0
    weak = 0
    current = token
    while True:
        stripped = current.strip()
        if len(stripped) >= 2 and stripped.startswith("{") and stripped.endswith("}"):
            strong += 1
            current = stripped[1:-1]
            continue
        if len(stripped) >= 2 and stripped.startswith("[") and stripped.endswith("]"):
            weak += 1
            current = stripped[1:-1]
            continue
        break
    return current.strip(), strong, weak


def _consume_leading_wrappers(token: str) -> Tuple[str, int, int]:
    strong = 0
    weak = 0
    i = 0
    length = len(token)
    while i < length:
        ch = token[i]
        if ch == "{":
            strong += 1
            i += 1
            continue
        if ch == "[":
            weak += 1
            i += 1
            continue
        if ch.isspace():
            i += 1
            continue
        break
    return token[i:].lstrip(), strong, weak


def _consume_trailing_wrappers(token: str) -> str:
    end = len(token)
    while end > 0:
        ch = token[end - 1]
        if ch in "}]":
            end -= 1
            continue
        if ch.isspace():
            end -= 1
            continue
        break
    return token[:end].rstrip()


_weighted_prompt_re = re.compile(
    r"^([+-]?(?:\d*\.\d+|\d+)?)\s*::\s*(.*?)(?:\s*::\s*)?$"
)


def _parse_prompt_token(
    raw_token: str,
    kind: str,
    *,
    weight_factor: float = 1.0,
    inherited_emphasis: Optional[str] = None,
) -> List[TagRecord]:
    token = raw_token.strip()
    if not token:
        return []

    strong = 0
    weak = 0

    token, balanced_strong, balanced_weak = _strip_balanced_wrappers(token)
    strong += balanced_strong
    weak += balanced_weak

    token, prefix_strong, prefix_weak = _consume_leading_wrappers(token)
    strong += prefix_strong
    weak += prefix_weak

    token = _consume_trailing_wrappers(token)

    local_weight = weight_factor
    if strong:
        local_weight *= 1.1 ** strong
    if weak:
        local_weight *= 0.9 ** weak

    emphasis: Optional[str] = inherited_emphasis
    if strong and not weak:
        emphasis = "strong"
    elif weak and not strong:
        emphasis = "weak"
    elif strong and weak:
        emphasis = "strong"

    if not token:
        return []

    subtokens = split_prompt(token)
    if len(subtokens) > 1:
        records: List[TagRecord] = []
        for sub in subtokens:
            records.extend(
                _parse_prompt_token(
                    sub,
                    kind,
                    weight_factor=local_weight,
                    inherited_emphasis=emphasis,
                )
            )
        return records

    weighted_match = _weighted_prompt_re.match(token)
    if weighted_match:
        numeric_str = weighted_match.group(1) or ""
        token = weighted_match.group(2).strip()
        emphasis = "weighted"
        try:
            numeric_value = float(numeric_str) if numeric_str not in {"", "+", "-"} else 1.0
        except ValueError:
            numeric_value = 1.0
        local_weight *= numeric_value

    if not token:
        return []

    norm = normalize_tag(token)
    if not norm:
        return []

    final_emphasis = emphasis or "normal"
    clean = token.strip()
    return [
        TagRecord(
            tag=clean,
            norm=norm,
            kind=kind,
            emphasis=final_emphasis,
            weight=local_weight,
            raw=raw_token.strip(),
        )
    ]


def parse_prompt(text: str, kind: str) -> List[TagRecord]:
    if not text:
        return []
    results: Dict[str, TagRecord] = {}
    for raw_token in split_prompt(text):
        for record in _parse_prompt_token(raw_token, kind):
            existing = results.get(record.norm)
            if existing is None or abs(record.weight) > abs(existing.weight):
                results[record.norm] = record
    return list(results.values())


def read_png_metadata(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    with path.open("rb") as fh:
        signature = fh.read(8)
        if signature != PNG_SIGNATURE:
            return out
        while True:
            length_bytes = fh.read(4)
            if not length_bytes:
                break
            length = int.from_bytes(length_bytes, "big")
            chunk_type = fh.read(4)
            data = fh.read(length)
            fh.read(4)  # CRC
            if chunk_type == b"IHDR" and length >= 8:
                width = int.from_bytes(data[0:4], "big")
                height = int.from_bytes(data[4:8], "big")
                out["Width"] = str(width)
                out["Height"] = str(height)
            elif chunk_type == b"tEXt":
                try:
                    key, value = data.split(b"\x00", 1)
                except ValueError:
                    continue
                out[key.decode("latin-1")] = value.decode("utf-8", "replace")
            elif chunk_type == b"iTXt":
                try:
                    nul = data.index(b"\x00")
                except ValueError:
                    continue
                key = data[:nul].decode("latin-1")
                if len(data) < nul + 2:
                    continue
                comp_flag = data[nul + 1]
                remainder = data[nul + 3 :]
                try:
                    lang_end = remainder.index(b"\x00")
                except ValueError:
                    continue
                remainder = remainder[lang_end + 1 :]
                try:
                    translated_end = remainder.index(b"\x00")
                except ValueError:
                    continue
                remainder = remainder[translated_end + 1 :]
                text_data = remainder
                if comp_flag:
                    import zlib

                    try:
                        text = zlib.decompress(text_data).decode("utf-8", "replace")
                    except Exception:
                        text = text_data.decode("utf-8", "replace")
                else:
                    text = text_data.decode("utf-8", "replace")
                out[key] = text
            elif chunk_type == b"zTXt":
                try:
                    key, remainder = data.split(b"\x00", 1)
                except ValueError:
                    continue
                text = remainder[1:]
                import zlib

                try:
                    value = zlib.decompress(text).decode("utf-8", "replace")
                except Exception:
                    value = text.decode("utf-8", "replace")
                out[key.decode("latin-1")] = value
            elif chunk_type == b"IEND":
                break
    return out


def load_comment_metadata(chunks: Dict[str, str]) -> Dict[str, object]:
    comment = chunks.get("Comment")
    if not comment:
        return {}
    try:
        return json.loads(comment)
    except json.JSONDecodeError:
        return {}


def collect_tags(chunks: Dict[str, str]) -> Tuple[List[TagRecord], Optional[str], Dict[str, object]]:
    comment_meta = load_comment_metadata(chunks)
    prompt_sources: List[Tuple[str, str]] = []
    description_text: Optional[str] = None
    if "Description" in chunks:
        description_text = chunks["Description"]
        prompt_sources.append((chunks["Description"], "description"))
    if isinstance(comment_meta.get("prompt"), str):
        prompt_sources.append((comment_meta["prompt"], "prompt"))
    v4_prompt = comment_meta.get("v4_prompt")
    if isinstance(v4_prompt, dict):
        base_caption = v4_prompt.get("caption", {}).get("base_caption")
        if base_caption:
            prompt_sources.append((base_caption, "prompt"))
        char_list = v4_prompt.get("caption", {}).get("char_captions", []) or []
        for char in char_list:
            if not isinstance(char, dict):
                continue
            cc = char.get("char_caption")
            if cc:
                prompt_sources.append((cc, "character"))
    negatives: List[str] = []
    uc = comment_meta.get("uc")
    if isinstance(uc, str):
        negatives.append(uc)
    v4_neg = comment_meta.get("v4_negative_prompt")
    if isinstance(v4_neg, dict):
        base_caption = v4_neg.get("caption", {}).get("base_caption")
        if base_caption:
            negatives.append(base_caption)
        for char in v4_neg.get("caption", {}).get("char_captions", []) or []:
            if isinstance(char, dict):
                cc = char.get("char_caption")
                if cc:
                    negatives.append(cc)
    tag_entries: List[TagRecord] = []
    for text, source_kind in prompt_sources:
        if source_kind == "character":
            tag_entries.extend(parse_prompt(text, "character"))
        else:
            tag_entries.extend(parse_prompt(text, "prompt"))
    for neg in negatives:
        tag_entries.extend(parse_prompt(neg, "negative"))
    dedup: Dict[Tuple[str, str], TagRecord] = {}
    order: List[Tuple[str, str]] = []
    for tag in tag_entries:
        key = (tag.kind, tag.norm)
        existing = dedup.get(key)
        if existing is None or abs(tag.weight) > abs(existing.weight):
            dedup[key] = tag
            if key not in order:
                order.append(key)
    combined = [dedup[key] for key in order]
    return combined, description_text, comment_meta


def parse_query_tokens(query: str) -> List[Tuple[str, str, bool]]:
    tokens: List[Tuple[str, str, bool]] = []
    if not query:
        return tokens
    for raw in re.split(r"[,\n]", query):
        token = raw.strip()
        if not token:
            continue
        exclude = False
        while token.startswith(("-", "!")):
            exclude = True
            token = token[1:].strip()
        kind = "any"
        lowered = token.lower()
        if lowered.startswith("char:"):
            kind = "character"
            token = token[5:].strip()
        elif lowered.startswith("character:"):
            kind = "character"
            token = token[10:].strip()
        elif lowered.startswith("prompt:"):
            kind = "prompt"
            token = token[7:].strip()
        elif lowered.startswith("uc:"):
            kind = "negative"
            token = token[3:].strip()
        while token.startswith(("-", "!")):
            exclude = True
            token = token[1:].strip()
        norm = normalize_tag(token)
        if not norm:
            continue
        tokens.append((norm, kind, exclude))
    return tokens
