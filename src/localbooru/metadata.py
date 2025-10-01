"""Metadata helpers for LocalBooru."""
from __future__ import annotations

from typing import Dict, List

from .tags import parse_prompt


def extract_character_details(metadata: Dict[str, object]) -> List[Dict[str, object]]:
    characters: List[Dict[str, object]] = []
    if not isinstance(metadata, dict):
        return characters
    v4_prompt = metadata.get("v4_prompt")
    if not isinstance(v4_prompt, dict):
        return characters
    caption = v4_prompt.get("caption")
    if not isinstance(caption, dict):
        return characters
    char_list = caption.get("char_captions") or []
    if not isinstance(char_list, list):
        return characters
    for idx, entry in enumerate(char_list):
        if not isinstance(entry, dict):
            continue
        caption_text = entry.get("char_caption") or ""
        tags = parse_prompt(caption_text, "character") if caption_text else []
        serialized_tags = [
            {
                "tag": tag.tag,
                "norm": tag.norm,
                "kind": tag.kind,
                "emphasis": tag.emphasis,
                "weight": tag.weight,
                "count": 0,
            }
            for tag in tags
        ]
        characters.append(
            {
                "index": idx,
                "caption": caption_text,
                "tags": serialized_tags,
                "centers": entry.get("centers") or [],
            }
        )
    return characters
