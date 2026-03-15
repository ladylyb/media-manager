# Manual QA Media Fixture

This fixture is the repository-owned manual testing dataset for planner/apply validation.

Use it when you want repeatable, visually obvious inputs instead of real photos.

## Regeneration

Regenerate the fixture with:

```bash
python3 tools/generate_manual_qa_media_fixture.py
```

The generator rebuilds the entire tree under `testdata/manual-qa/media-manager-v1/`.

## Why Regenerate Before QA

Some scenarios intentionally rely on the current runtime's filesystem-derived `TAKEN_DT` fallback because the default metadata extractor uses filesystem timestamps when readable embedded metadata is unavailable. Regenerating locally keeps the noop and collision cases aligned with the current planner behavior for this environment.

## Expected Scenario Summary

| Folder | Input count | Supported count | Expected behavior |
| --- | ---: | ---: | --- |
| `01_already_canonical_noop` | 4 | 4 | Mostly noop planning because files already sit in canonical-style destinations with generator-aligned filenames. |
| `02_inbox_moves_photos` | 7 | 7 | Clear photo move/rename actions from `inbox/photos` into `Media/Photos/<year>/<month>/`. |
| `03_inbox_moves_videos` | 4 | 4 | Clear video move/rename actions from `inbox/videos` into `Media/Videos/<year>/<month>/`. |
| `04_exact_duplicates` | 6 | 6 | Three exact duplicate pairs stored in different folders to make duplicate handling easy to inspect. |
| `05_unsupported_and_noise` | 5 | 0 | Deterministic skip behavior for unsupported extensions and extensionless files. |
| `06_collision_targets` | 4 | 4 | Two inbox items plus two preexisting destination files to validate `rename`, `skip`, and `fail` collision modes. |
| `07_unknown_date_and_mixed_metadata` | 4 | 4 | Supported media without embedded metadata; current extractor falls back to filesystem-derived dates rather than producing a true `unknown` bucket. |

## Naming Convention

Source files use:

`S<scenario>_<group>_<seq>__<signal>.<ext>`

Examples:

- `S02_photo_001__unique-red.jpg`
- `S03_video_001__unique-pan.mp4`
- `S04_dup01_a__same-bytes.jpg`
- `S05_noise_001__unsupported.txt`
- `S06_collide_001__target-match.jpg`

Signals are intentionally descriptive so you can compare planner/apply output against the filesystem without guessing.

## Validation Checklist

- Re-run plan twice and compare counts for determinism.
- Verify `01_already_canonical_noop` produces mostly noop results.
- Verify `02_inbox_moves_photos` and `03_inbox_moves_videos` move into canonical folders.
- Verify `05_unsupported_and_noise` produces skips only.
- Verify `04_exact_duplicates` stays stable across repeated runs.
- Run `06_collision_targets` with `rename`, `skip`, and `fail`.
- Confirm `rename` mode yields suffixed destinations such as `__dup01` during apply.
- Re-run plan/apply after completion and confirm the result shape remains easy to explain.
