# Content Rating Feature

## Overview

The content rating feature adds automatic classification of images into Danbooru-style rating categories: `general` (safe), `sensitive` (suggestive but non-explicit), `questionable` (mildly explicit), and `explicit` (NSFW). This enables global filtering for content maturity, helping users organize and browse galleries without manual tagging. Ratings are computed offline using a lightweight model, integrated as searchable tags, and exposed in the UI for easy toggling.

This is particularly useful for NovelAI-generated images, which often vary in explicitness. Ratings are stored per-image and can be queried like any tag (e.g., `-rating:explicit` to exclude NSFW).

## Technical Implementation

### Model and Computation
Rating data is produced directly by the WD14 tagger (`imgutils.tagging.wd14`). The model returns a probability for each Danbooru-style class; we cache the full distribution, surface the top class as a `rating:{class}` tag, and feed the complete confidences into the UI for detail-page bars.

- **Process**: Every time WD14 runs (inline or in the background queue) we persist the four probabilities, update `images.rating`/`images.rating_confidence`, and store a JSON blob in `rating_jobs.scores_json` for later inspection.
- **Fallback**: If you still prefer the standalone DBRating classifier, `--rate-missing` keeps the legacy pipeline enabled and we continue to update the same fields when DBRating completes.

Models for WD14 download automatically on first use and are cached under Hugging Face's hub directory. LocalBooru prefetches them during startup so connectivity issues surface early.

### Background Queue
Whenever WD14 runs in the background (`AutoTagIndexer`) we now capture rating information alongside general/character tags:

- **Queueing**: During ingestion (`ingestion.py`), we re-queue images that are missing a `rating:` tag so the WD14 worker can backfill them. This happens even if descriptive auto-tags already exist.
- **Batching**: `reserve_rating_batch(model, limit)` still supports the optional DBRating thread. If you keep it enabled, it will overwrite the WD14 rating with its own prediction and update the stored score map (WD14 data remains available for comparison).
- **Storage**: WD14 writes all four confidences into `rating_jobs.scores_json` and keeps the highest-confidence class synced to both `images.rating` and the `rating:{class}` tag (source `auto`).
- **Progress**: `RatingProgress` continues to expose queue status via `/api/rating_status` so you can monitor either WD14 backfills or DBRating runs.

### Database Storage
- **Schema**: `rating_jobs` table (image_id, status, model, rating, confidence, error, timestamps).
- **Images Table**: Adds `rating TEXT`, `rating_confidence REAL`, `rating_updated REAL` (via ALTER on upgrade).
- **Tags Table**: Inserts `kind="rating"` row for querying (e.g., norm="rating:explicit").
- **Queries**: Ratings integrate with FTS5 tag index for fast search/facets. Progress counts via SQL sums.

Example DB query: `SELECT i.path, i.rating, t.tag FROM images i LEFT JOIN tags t ON t.image_id=i.id AND t.kind='rating' WHERE i.rating='explicit';`

### Search Integration
Ratings behave like tags:
- **Querying**: Use `rating:general` or `-rating:explicit` in search box.
- **Facets**: Appear in sidebar "Tags" card (prioritized like prompts/characters).
- **Autocomplete**: Prefix "rating:" suggests classes with frequency.
- **Filtering**: Excludes/unincludes based on tokens; respects intersections (e.g., "cat rating:questionable").

No special syntax—leverages existing `search.py` (build_matched_cte, collect_tag_facets).

- ### UI Elements
- **Gallery Sidebar**:
- **Rating Filter Card**: Checkboxes for each class (default: check General/Sensitive/Questionable, uncheck Explicit). Each pill displays a live count (fed by `/api/rating_counts`) so the numbers refresh as new items are scanned or tagged. Toggling automatically injects or removes `-rating:{class}` exclusions.
- Status chips in the detail pane include a "Rating" entry that tracks queue position and readiness alongside CLIP and auto-tag states.

- **Detail Page**:
  - Badge below image info reflects the highest-confidence class and includes the percentage.
  - A bar chart shows all four confidences so you can see borderline cases at a glance.
  - Ratings are included in the copy/export buttons (e.g., `rating:explicit`).

CSS example (add to app.css):
```css
.rating-label { padding: 4px 8px; border-radius: 4px; font-weight: bold; }
.rating-label.general { background: #90EE90; color: #006400; }
.rating-label.sensitive { background: #FFD700; color: #8B4513; }
.rating-label.questionable { background: #FFA07A; color: #8B0000; }
.rating-label.explicit { background: #FF6B6B; color: white; }
.rating-filters label { display: block; margin: 4px 0; cursor: pointer; }
```

JS wiring: Event listeners on checkboxes trigger `applyToken` for search refresh; sync states from active tokens on load.

## CLI Flags
Ratings now piggyback on the WD14 auto-tag flow, so no extra CLI flags are required beyond the existing auto-tag options (e.g., `--auto-tag-missing`, `--auto-tag-mode`).

## Accuracy and Limitations
- **Performance**: ~10-50ms/image on CPU; batching helps. GPU not supported (imgutils CPU-only).
- **Accuracy**: Model benchmarks ~80-90% on test sets, but boundaries blurry (e.g., swimsuits as sensitive vs. questionable). Not ground truth—use for rough filtering.
- **NSFW Detection**: Best for anime; may misrate real photos. For stricter censoring, pair with `imgutils.detect.censor.detect_censors()`.
- **Edge Cases**: Corrupt images error out; unrated images show in all filters until processed. No re-rating on metadata changes (yet).
- **Privacy**: Fully local; no data sent externally.
- **Optional Extras**: If you want to compare against DBRating, install `imgutils[validate]` and re-enable `--rate-missing`. Otherwise WD14 alone populates all required data.

Future: Thresholds for scores, multi-model voting, manual override tags.

See `src/localbooru/rating.py` for code; report issues in AGENTS.md.
