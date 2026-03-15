

## Merge Discover + Gallery into a single "Gallery" screen

You're right — the two pages overlap significantly. Both show a grid of canonical media files with pagination. The only meaningful differences are:

- **Gallery** has a detail modal with metadata/tags and video support indicators
- **Discover** has tag-based filtering, sort controls, and URL-synced params

These combine naturally into one screen: a filterable, sortable media grid with a detail modal.

### Plan

1. **Merge Discover features into GalleryPage** — Add the tag filter bar (with autosuggest), sort controls, and URL-synced params from DiscoverPage into GalleryPage, placed above the existing grid.

2. **Keep Gallery's detail modal** — The click-to-open modal with metadata, tags, and video playback stays as-is.

3. **Show top tag on grid cards** — Carry over Discover's per-card tag badge so each thumbnail shows its top-confidence tag.

4. **Remove DiscoverPage** — Delete `src/pages/DiscoverPage.tsx`, remove its route from `App.tsx`, and remove the "Discover" entry from `AppSidebar.tsx` navigation.

5. **Update sidebar** — The Media section becomes just "Gallery" and "Duplicates".

This keeps the best of both pages without duplication, and reduces cognitive load for operators.

