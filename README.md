# localbooru

LocalBooru is a local-first AI-gen and meme gallery browser with CLIP-powered search, WD14 auto-tagging, and a lightweight web UI. It watches one or more directories, stores metadata in SQLite, and serves a faceted search experience entirely on your machine.

The clip search was inspired by [rclip](https://github.com/yurijmikhalevich/rclip)

WD14 tagging is provided by [deepghs/imgutils](https://github.com/deepghs/imgutils)

Non-novelAI AI tag extraction is done with sd-parsers so don't complain to me if your weird comfy workflow didn't parse correctly.

The whole project was almost entirely vibe-coded so it may have serious bugs, and I don't suggest exposing it to the internet.

## Installation

### Quick bootstrap

Run the helper script to create a virtual environment and install LocalBooru with all optional extras:

```bash
scripts/setup_venv.sh
source .venv/bin/activate
cd /your/gallery/location
```

Pick another location with `--venv /path/to/env`. Use `--backend cpu|cuda|rocm|mps` to select a torch stack; for GPU backends set `CUDA_VERSION` or `ROCM_VERSION` to match your wheels.

The script installs LocalBooru in editable mode, enables the CLIP, UI, and watch extras, and pulls in `dghs-imgutils` (GPU variant when applicable) for WD14 support.

### Manual install

Inside your preferred virtual environment:

```bash
pip install --upgrade pip wheel setuptools
pip install -e .[clip,ui,watch]
pip install dghs-imgutils  # or dghs-imgutils[gpu] for CUDA/ROCm torch wheels
```

The extras can be mixed and matched:

- `clip` – PyTorch + OpenCLIP for embeddings and semantic search
- `ui` – PyWebView for the optional desktop shell
- `watch` – watchdog/inotify backend (falls back to timed rescans when absent)
- `tagging` – WD14 auto-tagging helpers (installed automatically by the script above)

## Quick start

From your gallery location:

```bash
localbooru --cwd
```
This will scan and place the database in your current working directory.

### Configuration files & service deployments

If you want to run it more seriously...

Save an annotated template with:

```bash
localbooru --print-config > ~/.localbooru.toml

```

When `~/.localbooru.toml` exists it is loaded automatically (override with `--config` or `LOCALBOORU_CONFIG`; use `--cwd` to opt out of auto-discovery). Paths inside config files resolve relative to the config file itself. Key options:

- `root` for the primary library location.
- `extra_roots` appends more libraries.
- `db_path` and `thumb_cache` default to `${XDG_STATE_HOME:-~/.local/state}/localbooru/gallery.db` and `${XDG_CACHE_HOME:-~/.cache}/localbooru/thumbs` once a config file is in use.
- `watch = true` enables the background rescanner; combine with the `watch` extra for native filesystem events.
- `service = true` mirrors `--service` defaults (watch enabled, browser suppressed).
- `clip_*` controls model choice, batch size, and device.
- `auto_tag_*` toggles WD14 behaviour, thresholds, background processing, and batch size.


## Automatic tagging for unlabeled images

Install `dghs-imgutils` (or `dghs-imgutils[gpu]`) to let the WD14 queue run. Auto-tagging defaults to augmenting metadata in the background; tweak it via:

- `--no-auto-tag` (or `auto_tag_missing = false`) to disable entirely.
- `--auto-tag-mode missing|augment` to only fill empty tags.
- `--no-auto-tag-background` to run inline during ingestion.
- `--auto-tag-batch-size` to control background batch size (default 4).
- `--auto-tag-model`, `--auto-tag-general-threshold`, and `--auto-tag-character-threshold` for model selection and thresholds.

`localbooru --status` (or the spinning gear menu in the UI) exposes CLIP and WD14 progress snapshots.

## Tag search & filtering

The main search box supports tag-based queries with the following syntax:

- **Basic tags**: `cat, dog, forest` – finds images containing these tags
- **Negative tags**: `-cat, !dog` – excludes images with these tags  
- **Tag types**:
  - `prompt:cat` – search in prompt tags only
  - `char:alice` or `character:alice` – search character tags
  - `uc:watermark` – search negative prompt tags
  - `rating:safe` – search rating tags
- **Path search**:
  - `path:Downloads` – find files with paths containing "Downloads"
  - `path:birds/` – find files in any "birds" directory  
  - `path:/home/user/Images/*` – explicit wildcards for exact patterns
  - `path:*/temp/*` – explicit directory matching
  - `in:Downloads` – alias for path search
  - `-path:temp` – exclude paths containing "temp"

Path patterns support:

- Auto-wildcards: `path:pol` becomes `*pol*`
- Directory search: `path:birds/` becomes `*/birds/*`
- Explicit wildcards: `path:*pol*` stays as-is (user controls pattern)
- `*` matches any characters, `?` matches single characters
- Absolute paths are normalized relative to configured roots
- Case-sensitive matching

Multiple search terms are combined with AND logic. Separate terms with commas or newlines.

## CLIP search & similarity

- Use the "CLIP search…" box in the header to run semantic text queries; active tag filters still apply.
- Every card (and the detail overlay) includes a **Find Similar** button that reuses stored embeddings to pull visually related images.
- Disable embeddings with `--no-clip` (or `clip_enabled = false`) when you want a metadata-only workflow; the UI will automatically hide CLIP controls.
- `--clip-device` selects the torch device (e.g. `cuda`, `cuda:1`, `mps`); adjust `--clip-batch-size` when GPU memory is tight.

## Torch stacks (optional manual install)

If you are not using `scripts/setup_venv.sh`, install a matching torch stack before or after installing LocalBooru:

- **CPU-only**:
  ```bash
  pip install --extra-index-url https://download.pytorch.org/whl/cpu \
      torch torchvision torchaudio
  ```
- **NVIDIA CUDA** (`cu121` shown; replace as needed):
  ```bash
  pip install --index-url https://download.pytorch.org/whl/cu121 \
      torch torchvision torchaudio
  ```
- **AMD ROCm** (`rocm6.1` shown):
  ```bash
  pip install --index-url https://download.pytorch.org/whl/rocm6.1 \
      torch torchvision torchaudio
  ```
- **Apple Silicon (MPS)**:
  ```bash
  pip install torch torchvision torchaudio
  ```

Then add `open_clip_torch` and `pywebview` if you skipped the extras:

```bash
pip install open_clip_torch pywebview
```

Missing dependencies cause the CLI to fail fast with an explanatory error.
