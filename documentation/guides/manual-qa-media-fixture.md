# Manual QA Media Fixture

Use the local fixture generator when you want a repeatable test media library
for planner/apply validation without using real photos and videos.

## What It Creates

The generator builds a local-only dataset under:

`testdata/manual-qa/media-manager-v1/`

That dataset includes:

- already-canonical media for mostly-noop runs
- inbox photos and videos that should move into canonical folders
- exact duplicate pairs
- unsupported files that should be skipped
- collision-target scenarios for `rename`, `skip`, and `fail`
- mixed metadata and filesystem-fallback cases

The generated media files are ignored by git and should not be committed.

## How To Generate It

Run:

```bash
python3 tools/generate_manual_qa_media_fixture.py
```

Requirements:

- `ffmpeg` must be installed on the machine running the script

## How To Use It

Point the Pipeline Wizard or other local testing flow at:

`/home/harish/projects/media-manager/testdata/manual-qa/media-manager-v1`

Suggested checks:

- re-run plan twice and compare the result shape for determinism
- inspect noop behavior in the already-canonical scenario
- inspect move behavior for inbox photos and videos
- verify unsupported files are skipped
- test duplicate handling and collision modes

## Why It Is Local-Only

The fixture includes generated binary media files. Keeping those outputs out of
source control avoids unnecessary repository churn while preserving a
repeatable, tool-driven way to recreate the same testing structure locally.
