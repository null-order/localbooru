# localbooru

Prototype package for the combined NovelAI gallery + CLIP search tool.

> **Status:** core scaffolding in progress – filesystem ingestion, CLIP indexing queue, status API, and placeholder UI are in place. Search endpoints and the full gallery UI will land next.

## Usage

```bash
python -m localbooru.cli --help
```

Typical workflow during development:

```bash
# initial scan + background services
python -m localbooru.cli --root /path/to/novelai --db /tmp/localbooru.db --watch

# query CLIP status
python -m localbooru.cli --status --db /tmp/localbooru.db

# rebuild embeddings only
python -m localbooru.cli --clip-only --db /tmp/localbooru.db
```

Launching without `--no-ui` will attempt to open a frameless `pywebview` window (install via `pip install localbooru[ui]`). CLIP indexing requires the optional extras (`pip install localbooru[clip]`).

## CLIP search & similarity

- Use the "CLIP search…" box in the header to run semantic text queries; active tag filters still apply so you can mix both worlds.
- Every card (and the detail overlay) includes a **Find Similar** button that reuses stored embeddings to pull visually related images.
- When CLIP support is disabled (`--no-clip` or missing extras) the UI controls are disabled automatically while the rest of the gallery continues to function.

### Required dependencies

Runtime now expects CPU builds of PyTorch, OpenCLIP, and PyWebView. Install them once (before or after `pip install localbooru`):

```bash
export PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu
pip install --break-system-packages torch open_clip_torch pywebview
```

`localbooru` will raise an explicit error if any of these modules are missing at startup.
