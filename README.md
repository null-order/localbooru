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

`localbooru` now expects PyTorch, OpenCLIP, and PyWebView to be present at runtime. Install **one** of the following stacks before (or after) installing the package:

- **CPU-only** (works everywhere):
  ```bash
  export PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu
  pip install --break-system-packages torch open_clip_torch pywebview
  ```
- **NVIDIA CUDA** (replace `cu121` with the desired CUDA version):
  ```bash
  pip install --break-system-packages \
      torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
  pip install --break-system-packages open_clip_torch pywebview
  ```
- **AMD ROCm** (install ROCm, then grab the matching wheels):
  ```bash
  pip install --break-system-packages torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.1
  pip install --break-system-packages open_clip_torch pywebview
  ```
- **Apple Silicon (MPS)**:
  ```bash
  pip install --break-system-packages torch torchvision open_clip_torch pywebview
  ```

If any of these modules are missing at startup, the CLI will fail fast with an explanatory error.
