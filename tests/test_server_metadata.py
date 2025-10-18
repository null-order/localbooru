from __future__ import annotations

import json
from http import HTTPStatus
from types import SimpleNamespace

from localbooru.database import LocalBooruDatabase
from localbooru.server import LocalBooruRequestHandler


class _StubHandler(LocalBooruRequestHandler):
    """Thin test double that skips BaseHTTPRequestHandler setup."""

    def __init__(self, db: LocalBooruDatabase) -> None:
        # Avoid BaseHTTPRequestHandler.__init__; set only what we need.
        self.server = SimpleNamespace(db=db)
        self.command = "GET"
        self.path = "/api/image/1"
        self.responses: list[dict] = []

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:  # type: ignore[override]
        self.responses.append({"status": status, "payload": payload})

    def send_error(self, code: int, message: str, explain: str | None = None) -> None:  # type: ignore[override]
        raise AssertionError(f"send_error called: {code} {message}")

    def log_message(self, format: str, *args: object) -> None:  # type: ignore[override]
        # Suppress BaseHTTPRequestHandler log output during tests.
        return


def test_image_detail_uses_comment_meta_for_characters(tmp_path) -> None:
    db_path = tmp_path / "gallery.db"
    db = LocalBooruDatabase(db_path)
    metadata_payload = {
        "prompt": "heroine, dramatic lighting",
        "comment_meta": {
            "v4_prompt": {
                "caption": {
                    "base_caption": "heroine, dramatic lighting",
                    "char_captions": [
                        {
                            "char_caption": "character:alice, {brave}",
                            "centers": [[0.5, 0.5]],
                        }
                    ],
                }
            }
        },
    }
    image_id, _changed = db.upsert_image_record(
        rel_path="hero.png",
        name="hero.png",
        mtime=0.0,
        size=123,
        width=512,
        height=512,
        seed=None,
        model=None,
        source=None,
        description=None,
        metadata_json=json.dumps(metadata_payload),
        tags=[],
    )

    handler = _StubHandler(db)
    handler._handle_image_detail(str(image_id))
    assert handler.responses, "expected JSON response"
    payload = handler.responses[0]["payload"]

    # Characters should be populated from comment_meta.v4_prompt.
    characters = payload["characters"]
    assert characters, "expected characters extracted from comment metadata"
    assert characters[0]["caption"] == "character:alice, {brave}"
    assert characters[0]["tags"], "character tags should be parsed from caption"

    # Prompt should still surface from the stored metadata payload.
    assert payload["prompts"]["positive"] == "heroine, dramatic lighting"

    db.close()
