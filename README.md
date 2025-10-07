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

Launching without `--no-ui` now opens the gallery in your default browser. Opt back into the embedded shell with `--webview` (install via `pip install localbooru[ui]` if you want that route). CLIP indexing requires the optional extras (`pip install localbooru[clip]`).

### Automatic tagging for unlabeled images

Install the WD14 helpers (`pip install localbooru[tagging]`) to let the bundled WD14 queue run by default. Auto-tagging now starts in augment + background mode out of the box; tweak it via:

- `--no-auto-tag` to opt out entirely, or `--auto-tag-mode missing` to only fill empty metadata slots.
- `--no-auto-tag-background` to run synchronously during ingestion (`--auto-tag-batch-size` still applies when backgrounded).
- `--auto-tag-model`, `--auto-tag-general-threshold`, and `--auto-tag-character-threshold` to tweak model selection and confidence cutoffs.
- The default model is SmilingWolf’s `ConvNextV2`; other installed variants (e.g. `ViT`, `MOAT`, `EVA02_Large`) can be selected with `--auto-tag-model`.

Use `localbooru --status` (or the new spinning gear menu in the UI) to inspect both CLIP and auto-tag queue progress.

On the detail view you'll now see status chips for CLIP/Tag state, plus auto-generated prompts (with NovelAI and Danbooru copy buttons) whenever an image only has WD14-sourced tags.

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
