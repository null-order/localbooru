# Repository Guidelines

## Project Structure & Module Organization
The package lives under `src/localbooru`, with `cli.py`, `server.py`, and `search.py` coordinating ingestion, HTTP endpoints, and CLIP lookup. Asset bundles reside in `frontend/`, static files in `static/`, and Jinja templates in `templates/`. Generated wheels drop in `dist/`; configuration defaults live in `config.py` and backing storage helpers in `database.py`.

## Build, Test, and Development Commands
Install editable dependencies with extras before contributing: `pip install -e .[clip,ui]`. Use `python -m localbooru.cli --help` to inspect available flags, or launch a full session via `python -m localbooru.cli --root <novelai_dir> --db ~/.local/localbooru.db --watch`. Rebuild embeddings only with `python -m localbooru.cli --clip-only --db <path>`; run a headless rescan with `--scan-only --no-ui` to avoid spawning the webview.

## Coding Style & Naming Conventions
Follow PEP 8 with Black-compatible 4-space indentation. Keep module-level constants `UPPER_SNAKE_CASE`, classes `PascalCase`, and functions plus CLI flags `snake_case`. Prefer explicit imports from sibling modules (e.g., `from .scanner import Scanner`). When touching UI assets, mirror existing Vite-style naming in `frontend/` and camelCase React component files.

## Testing Guidelines
Add new pytest suites under a top-level `tests/` package, mirroring the `localbooru` module path. Name files `test_<feature>.py` and include regression fixtures for database schema changes. Use temporary SQLite files and sample PNGs in `/tmp` to keep runs hermetic. Execute `pytest` locally before opening a pull request and document notable coverage gaps in the PR body.

## Commit & Pull Request Guidelines
Match the existing imperative, present-tense subject lines (e.g., `Add drag and drop CLIP search`). Group related changes and avoid drive-by refactors. Every PR should include a short summary, reproduction or validation steps, and screenshots of UI tweaks (capture both light/dark states when possible). Link tracking issues with GitHub keywords and request review from a maintainer familiar with the touched subsystem.

## Security & Configuration Tips
Never commit NovelAI assets or personal galleries; use sample placeholders in `tests/fixtures`. Treat `.db` paths as disposable and prefer storing credentials in environment variables consumed by `LocalBooruConfig`. Verify new optional dependencies are guarded behind extras to keep the base install lean.
