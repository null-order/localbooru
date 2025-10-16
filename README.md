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

### Configuration files & service mode

Point the CLI at a JSON/TOML/YAML configuration file with `--config` (or the `LOCALBOORU_CONFIG` environment variable) to pin down long-lived installs. When no explicit path is provided, LocalBooru automatically looks for `~/.localbooru.toml` (unless you opt into `--cwd` legacy mode). Example TOML:

```toml
roots = [
  "/mnt/library/novelai",
  "/mnt/library/reference",
]
watch = true      # enable background rescans
service = true    # skip UI launch and favour watch mode defaults
```

The first entry in `roots` becomes the primary ingest root; the rest are treated as additional libraries. `extra_roots` can be supplied alongside the list if you prefer to keep the old split.

When a config file is present and no explicit database path is provided, LocalBooru now stores metadata under `${XDG_STATE_HOME:-~/.local/state}/localbooru/gallery.db`. Thumbnails continue to live under `${XDG_CACHE_HOME:-~/.cache}/localbooru/thumbs`.

Print a fully annotated template with:

```bash
python -m localbooru.cli --print-config
```

Start a headless service with:

```bash
python -m localbooru.cli --config ~/.config/localbooru.toml --service
```

Install the optional watcher extra (`pip install localbooru[watch]`) to switch watch mode over to the `watchdog`/inotify backend. When the dependency is unavailable, the timer-based rescans from earlier releases remain in place. Use `--cwd` to stick with the original cwd-relative defaults and skip automatic config discovery.

### Full environment setup

LocalBooru offers the best experience when all optional extras are installed:

- `[clip]` provides OpenCLIP embedding support (torch + open_clip_torch)
- `[ui]` enables the optional desktop webview
- `[tagging]` adds WD14 auto-tagging
- `[watch]` swaps interval rescans for watchdog/inotify monitoring

Bootstrap everything in one go with the helper script (defaults to `.venv` in the repo root):

```bash
scripts/setup_venv.sh
source .venv/bin/activate
python -m localbooru.cli --config ~/.localbooru.toml
```

Pass a custom path (`scripts/setup_venv.sh --venv ~/localbooru-env`) or override the interpreter (`PYTHON=python3.11 scripts/setup_venv.sh`) when needed. The script installs LocalBooru in editable mode with all extras so development and full functionality share the same environment. CPU wheels are installed by default; pick another backend with `--backend cuda|rocm|mps` (set `CUDA_VERSION` or `ROCM_VERSION` to target a specific wheel tag).

The helper installs CLIP, UI, watchdog, and WD14 tagging support (using `dghs-imgutils`, or `dghs-imgutils[gpu]` for CUDA/ROCm). If you build environments manually, install the matching `dghs-imgutils` wheel yourself to enable auto-tagging.

### Automatic tagging for unlabeled images

Install the WD14 helpers (`pip install dghs-imgutils`, or `dghs-imgutils[gpu]` when running a CUDA/ROCm torch build) to let the bundled WD14 queue run by default. Auto-tagging now starts in augment + background mode out of the box; tweak it via:

- `--no-auto-tag` to opt out entirely, or `--auto-tag-mode missing` to only fill empty metadata slots.
- `--no-auto-tag-background` to run synchronously during ingestion (`--auto-tag-batch-size` still applies when backgrounded).
- `--auto-tag-model`, `--auto-tag-general-threshold`, and `--auto-tag-character-threshold` to tweak model selection and confidence cutoffs.
- The default model is SmilingWolf’s `ConvNextV2`; other installed variants (e.g. `ViT`, `MOAT`, `EVA02_Large`) can be selected with `--auto-tag-model`.

Use `localbooru --status` (or the new spinning gear menu in the UI) to inspect both CLIP and auto-tag queue progress.

On the detail view you'll now see status chips for CLIP/Tag state, plus auto-generated prompts (with NovelAI and Danbooru copy buttons) whenever an image only has WD14-sourced tags.

## Tag search & filtering

The main search box supports tag-based queries with the following syntax:

- **Basic tags**: `cat, dog, forest` - finds images containing these tags
- **Negative tags**: `-cat, !dog` - excludes images with these tags  
- **Tag types**: 
  - `prompt:cat` - search in prompt tags only
  - `char:alice` or `character:alice` - search character tags
  - `uc:watermark` - search negative prompt tags
  - `rating:safe` - search rating tags
- **Path search**:
  - `path:Downloads` - find files with paths containing "Downloads"
  - `path:birds/` - find files in any "birds" directory  
  - `path:/home/user/Images/*` - explicit wildcards for exact patterns
  - `path:*/temp/*` - explicit directory matching
  - `in:Downloads` - alias for path search
  - `-path:temp` - exclude paths containing "temp"

Path patterns support:
- Auto-wildcards: `path:pol` becomes `*pol*` (contains "pol")
- Directory search: `path:birds/` becomes `*/birds/*` (birds directory)
- Explicit wildcards: `path:*pol*` stays as-is (user controls pattern)
- `*` matches any characters, `?` matches single characters
- Absolute paths are normalized relative to configured roots
- Case-sensitive matching

Multiple search terms are combined with AND logic. Separate terms with commas or newlines.

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
