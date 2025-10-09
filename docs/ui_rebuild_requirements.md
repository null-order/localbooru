# UI Rebuild Requirements

## Layout & Structure
- Split the header into two equal-width inputs: the primary tag search and the CLIP search. Each gets an inline “×” clear icon (no separate search button). Pressing Enter still commits the search.
- Move the background status gear to the far right of the header. Clicking it toggles a fixed sidebar card (not a floating popover) that stacks above the tags list.
- Sidebar layout: the top card shows CLIP progress (state, rate, pause toggle) and auto-tagging progress (mode, counts, recent errors). Beneath it sits the tags card with a “UC Tags” pill-style toggle in the header.
- Remove the old control row (Clear button, checkbox). Keep the header status text to the left of the gear.
- Add a toast stack (top-right, persistent across navigation) for CLIP/indexer errors and notices, each dismissible with “×”.
- Gallery cards retain the “≈” similar button. Cards and detail metadata show a filename when seed/model are missing (filename truncated where appropriate).

## Tag Visibility & Autocomplete
- “UC Tags” toggle defaults to hiding UC (negative) facets. When enabled, negative facets reappear. The pill switches between a green border (visible) and red strikethrough (hidden).
- Tag clicks in gallery or detail apply the token without reopening the suggestion list. Autocomplete closes on blur and only opens on typing/focus.
- Suggestions remain keyboard navigable (↑/↓/Enter/Esc) and anchor under the tag search input.

## Detail Modal
- Keep the modal within the viewport (no page scrolling). Reduce padding and constrain height so tall images scale down. When scaled, use a zoom-in cursor; clicking opens the full image in a new tab (no extra “Full size” button).
- Use the same “≈” icon to the left of the metadata column for “Find Similar”; default disabled until CLIP is available.
- Allow the info column to extend into the footer area. The footer itself spans only beneath the image with Prev/Count/Next aligned left/center/right. Close button should be an “×” in the top-right corner.
- Preserve prompt, description, tags, and character sections styling; UC pill visibility respects the toggle.

## Search & CLIP Behavior
- Tag search commits instantly with Enter; the clear icon empties and re-runs the query.
- CLIP search runs live (debounced) on input changes; Enter reruns the current payload. Clearing exits clip mode but retains history state.
- When clip mode is active and the user edits the tag search, issue a combined clip+tag search, preserving the clip token in the URL/history.
- Browser back/forward should restore both query inputs and the correct results (including clip mode). Navigating back to an empty state reloads default gallery results, not stale data.
- Dropping an image triggers “find similar” via CLIP and shows the drop overlay instructions.

## Status Handling
- Background gear toggles the sidebar card open/closed; Esc closes it. Auto status card hides when disabled or in error state.
- Dismissing CLIP error toasts clears the error state (no lingering banners after dismissal).
- Continue polling `/api/status/clip` and `/api/status/auto` every 2 seconds. Toasts dismiss automatically on success or manually.

## Facets & Seeds
- Ensure both cards and detail metadata prefer seed/model. If no seed, show a truncated filename (same rules on gallery cards).
- Facet list filters honor the UC toggle; highlighting and hover behavior remain intact.

## Server & Logging
- Log `/api/status/clip` and `/api/status/auto` GET requests at DEBUG level.
- HTTP server should expose CLIP and auto-tag queue data for the sidebar cards (existing endpoints already provide totals, processing, queued, etc.).
- Watcher/scanner continues to prune missing files at startup/watch and enqueue new files for CLIP/auto-tagging.

## Styling Notes
- Match the previously shipped look: blurred sticky header, pill buttons, smooth transitions, Inter font, contain object-fit images.
- Sidebar cards emulate the Vite-like style with subtle glows; tags remain pill buttons with source/weight indicators.

## Testing Expectations
Manual smoke pass:
1. Toggle UC Tags and verify negative facets/tags hide/show without reopening suggestions.
2. Run a CLIP search, modify tags, confirm combined clip+tag results with `clip=` in the URL.
3. Open the detail modal on a tall image—ensure scaling, click-to-open, and “≈” behavior.
4. Toggle the status gear to reveal CLIP/auto sections; test pause/resume for CLIP.
5. Trigger and dismiss CLIP error toasts; ensure state resets.
6. Use browser back to restore inputs/results correctly (including empty state reset).

Existing pytest coverage must remain green; no regressions in ingestion/watch logic.
