"""Generate a local manual-QA media fixture under `testdata/manual-qa/`.

The generated files are intentionally local-only and are ignored by git. Use
this when you want a repeatable media dataset for planner/apply testing without
checking binary fixture payloads into source control.
"""

from __future__ import annotations

import sys
import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "testdata" / "manual-qa" / "media-manager-v1"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def infer_media_type_from_extension(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".bmp", ".tif", ".tiff", ".webp"}:
        return "IMG"
    if suffix in {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".wmv", ".3gp", ".webm"}:
        return "VID"
    return None


def generate_canonical_filename(
    *,
    media_type: str,
    taken_datetime: datetime,
    extension: str,
    owner: str = "LL",
    context: str = "General",
) -> str:
    ext = extension.lower()
    if ext.startswith("."):
        ext = ext[1:]
    return (
        f"{media_type.upper()}_"
        f"{taken_datetime.astimezone(UTC).strftime('%Y%m%d_%H%M%S')}_"
        f"{owner}_{context}.{ext}"
    )


@dataclass(frozen=True)
class CreatedFile:
    relative_path: str
    scenario: str
    kind: str
    note: str


def _run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return
    raise RuntimeError(result.stderr.strip() or f"ffmpeg failed: {' '.join(args)}")


def _drawtext_filter(label: str) -> str:
    safe = label.replace("\\", "\\\\").replace(":", r"\:").replace("'", r"\'")
    return (
        "drawtext="
        f"text='{safe}':"
        "fontcolor=white:fontsize=24:"
        "box=1:boxcolor=black@0.45:boxborderw=12:"
        "x=(w-text_w)/2:y=(h-text_h)/2"
    )


def _create_image(path: Path, *, color: str, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    vf = _drawtext_filter(label)
    args = [
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s=640x360:d=1",
        "-frames:v",
        "1",
        "-vf",
        vf,
        str(path),
    ]
    try:
        _run_ffmpeg(args)
    except RuntimeError:
        _run_ffmpeg(
            [
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=640x360:d=1",
                "-frames:v",
                "1",
                str(path),
            ]
        )


def _create_video(path: Path, *, color: str, label: str, duration_s: float = 1.5) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    vf = _drawtext_filter(label)
    args = [
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s=640x360:d={duration_s}",
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(path),
    ]
    try:
        _run_ffmpeg(args)
    except RuntimeError:
        _run_ffmpeg(
            [
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=640x360:d={duration_s}",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(path),
            ]
        )


def _create_heic_placeholder(path: Path, *, color: str, label: str) -> None:
    temp = path.with_suffix(".jpg")
    _create_image(temp, color=color, label=label)
    data = temp.read_bytes()
    temp.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _taken_datetime_from_fs(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_ctime, tz=UTC)


def _canonical_filename_for(path: Path) -> str:
    media_type = infer_media_type_from_extension(path)
    if media_type is None:
        raise ValueError(f"unsupported canonical filename generation for {path}")
    return generate_canonical_filename(
        media_type=media_type,
        taken_datetime=_taken_datetime_from_fs(path),
        extension=path.suffix,
        owner="LL",
        context="General",
    )


def _canonical_dir_for(base_root: Path, path: Path) -> Path:
    media_type = infer_media_type_from_extension(path)
    taken_dt = _taken_datetime_from_fs(path)
    if media_type == "VID":
        return base_root / "Media" / "Videos" / taken_dt.strftime("%Y") / taken_dt.strftime("%m")
    return base_root / "Media" / "Photos" / taken_dt.strftime("%Y") / taken_dt.strftime("%m")


def _stabilize_canonical_name(path: Path) -> Path:
    candidate = path
    for _ in range(4):
        desired_name = _canonical_filename_for(candidate)
        if candidate.name == desired_name:
            return candidate
        target = candidate.with_name(desired_name)
        candidate.rename(target)
        candidate = target
    return candidate


def _relative(path: Path) -> str:
    return str(path.relative_to(FIXTURE_ROOT).as_posix())


def _create_photo(path: Path, *, color: str, label: str) -> None:
    if path.suffix.lower() == ".heic":
        _create_heic_placeholder(path, color=color, label=label)
        return
    _create_image(path, color=color, label=label)


def _create_supported_media(path: Path, *, color: str, label: str) -> None:
    if path.suffix.lower() in {".mp4", ".mov"}:
        _create_video(path, color=color, label=label)
        return
    _create_photo(path, color=color, label=label)


def _scenario_01(created: list[CreatedFile]) -> None:
    base = FIXTURE_ROOT / "01_already_canonical_noop"
    planned = [
        (base / "Media" / "Photos" / "2024" / "01" / "seed_photo_01.jpg", "red", "NOOP PHOTO 01", "photo"),
        (base / "Media" / "Photos" / "2024" / "01" / "seed_photo_02.png", "blue", "NOOP PHOTO 02", "photo"),
        (base / "Media" / "Photos" / "2023" / "12" / "seed_photo_03.jpeg", "green", "NOOP PHOTO 03", "photo"),
        (base / "Media" / "Videos" / "2024" / "01" / "seed_video_01.mp4", "purple", "NOOP VIDEO 01", "video"),
    ]
    for path, color, label, kind in planned:
        _create_supported_media(path, color=color, label=label)
        final_path = _stabilize_canonical_name(path)
        created.append(CreatedFile(_relative(final_path), "01_already_canonical_noop", kind, "already-canonical seed"))


def _scenario_02(created: list[CreatedFile]) -> None:
    base = FIXTURE_ROOT / "02_inbox_moves_photos" / "inbox" / "photos"
    specs = [
        ("S02_photo_001__unique-red.jpg", "red", "PHOTO 001"),
        ("S02_photo_002__unique-blue.jpeg", "blue", "PHOTO 002"),
        ("S02_photo_003__unique-green.png", "green", "PHOTO 003"),
        ("S02_photo_004__unique-amber.heic", "yellow", "PHOTO 004"),
        ("S02_photo_005__unique-cyan.jpg", "cyan", "PHOTO 005"),
        ("S02_photo_006__unique-magenta.png", "magenta", "PHOTO 006"),
        ("S02_photo_007__unique-slate.jpeg", "gray", "PHOTO 007"),
    ]
    for filename, color, label in specs:
        path = base / filename
        _create_supported_media(path, color=color, label=label)
        created.append(CreatedFile(_relative(path), "02_inbox_moves_photos", "photo", "unique photo move candidate"))


def _scenario_03(created: list[CreatedFile]) -> None:
    base = FIXTURE_ROOT / "03_inbox_moves_videos" / "inbox" / "videos"
    specs = [
        ("S03_video_001__unique-pan.mp4", "orange", "VIDEO 001"),
        ("S03_video_002__unique-tilt.mov", "navy", "VIDEO 002"),
        ("S03_video_003__unique-zoom.mp4", "teal", "VIDEO 003"),
        ("S03_video_004__unique-track.mov", "brown", "VIDEO 004"),
    ]
    for filename, color, label in specs:
        path = base / filename
        _create_supported_media(path, color=color, label=label)
        created.append(CreatedFile(_relative(path), "03_inbox_moves_videos", "video", "unique video move candidate"))


def _scenario_04(created: list[CreatedFile]) -> None:
    base = FIXTURE_ROOT / "04_exact_duplicates"
    originals = [
        (base / "group_a" / "S04_dup01_a__same-bytes.jpg", "pink", "DUP 01", "photo", base / "group_b" / "S04_dup01_b__same-bytes-copy.jpg"),
        (base / "group_c" / "S04_dup02_a__same-bytes.mp4", "black", "DUP 02", "video", base / "group_d" / "S04_dup02_b__same-bytes-copy.mp4"),
        (base / "group_e" / "S04_dup03_a__same-bytes.png", "white", "DUP 03", "photo", base / "group_f" / "S04_dup03_b__same-bytes-copy.png"),
    ]
    for source, color, label, kind, duplicate in originals:
        _create_supported_media(source, color=color, label=label)
        duplicate.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, duplicate)
        created.append(CreatedFile(_relative(source), "04_exact_duplicates", kind, "duplicate source A"))
        created.append(CreatedFile(_relative(duplicate), "04_exact_duplicates", kind, "duplicate source B exact-byte copy"))


def _scenario_05(created: list[CreatedFile]) -> None:
    base = FIXTURE_ROOT / "05_unsupported_and_noise" / "noise"
    payloads = {
        "S05_noise_001__unsupported.txt": "manual qa unsupported text\n",
        "S05_noise_002__unsupported.csv": "id,value\n1,alpha\n2,beta\n",
        "S05_noise_003__unsupported.json": '{\n  "fixture": "manual-qa",\n  "supported": false\n}\n',
        "S05_noise_004__unsupported.abcx": "non-media custom extension\n",
        "S05_noise_005__unsupported": "extensionless payload\n",
    }
    for filename, content in payloads.items():
        path = base / filename
        _write_text(path, content)
        created.append(CreatedFile(_relative(path), "05_unsupported_and_noise", "noise", "unsupported input"))


def _scenario_06(created: list[CreatedFile]) -> None:
    base = FIXTURE_ROOT / "06_collision_targets"
    inbox_photo = base / "inbox" / "photos" / "S06_collide_001__target-match.jpg"
    inbox_video = base / "inbox" / "videos" / "S06_collide_002__target-match.mp4"

    _create_supported_media(inbox_photo, color="gold", label="COLLIDE 001")
    _create_supported_media(inbox_video, color="darkgreen", label="COLLIDE 002")

    photo_target = _canonical_dir_for(base, inbox_photo) / _canonical_filename_for(inbox_photo)
    video_target = _canonical_dir_for(base, inbox_video) / _canonical_filename_for(inbox_video)
    _write_bytes(photo_target, b"preexisting-photo-collision-target\n")
    _write_bytes(video_target, b"preexisting-video-collision-target\n")

    created.append(CreatedFile(_relative(inbox_photo), "06_collision_targets", "photo", "collision inbox photo"))
    created.append(CreatedFile(_relative(inbox_video), "06_collision_targets", "video", "collision inbox video"))
    created.append(CreatedFile(_relative(photo_target), "06_collision_targets", "photo", "preexisting collision target"))
    created.append(CreatedFile(_relative(video_target), "06_collision_targets", "video", "preexisting collision target"))


def _scenario_07(created: list[CreatedFile]) -> None:
    base = FIXTURE_ROOT / "07_unknown_date_and_mixed_metadata" / "inbox" / "mixed"
    specs = [
        ("S07_photo_001__no-exif-fallback.jpg", "salmon", "NO EXIF 001", "photo"),
        ("S07_photo_002__filename-date-20240214.png", "steelblue", "FALLBACK 002", "photo"),
        ("S07_video_003__fs-fallback.mp4", "indigo", "FALLBACK 003", "video"),
        ("S07_photo_004__heic-no-exif.heic", "khaki", "FALLBACK 004", "photo"),
    ]
    for filename, color, label, kind in specs:
        path = base / filename
        _create_supported_media(path, color=color, label=label)
        created.append(
            CreatedFile(
                _relative(path),
                "07_unknown_date_and_mixed_metadata",
                kind,
                "no embedded metadata; current extractor will fall back to filesystem-derived TAKEN_DT",
            )
        )


def _write_manifest(created: list[CreatedFile]) -> None:
    by_scenario: dict[str, dict[str, object]] = {}
    for item in created:
        abs_path = FIXTURE_ROOT / item.relative_path
        scenario = by_scenario.setdefault(
            item.scenario,
            {
                "file_count": 0,
                "supported_count": 0,
                "unsupported_count": 0,
                "files": [],
            },
        )
        scenario["file_count"] = int(scenario["file_count"]) + 1
        if item.kind == "noise":
            scenario["unsupported_count"] = int(scenario["unsupported_count"]) + 1
        else:
            scenario["supported_count"] = int(scenario["supported_count"]) + 1
        cast_files = list(scenario["files"])
        cast_files.append(
            {
                "path": item.relative_path,
                "kind": item.kind,
                "note": item.note,
                "sha256": _file_sha256(abs_path),
            }
        )
        scenario["files"] = sorted(cast_files, key=lambda row: row["path"])

    manifest = {
        "fixture_root": "testdata/manual-qa/media-manager-v1",
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "generator": "tools/generate_manual_qa_media_fixture.py",
        "scenarios": by_scenario,
    }
    (FIXTURE_ROOT / "fixture_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_expectations_readme() -> None:
    content = """# Manual QA Media Fixture

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
"""
    _write_text(FIXTURE_ROOT / "00_README_EXPECTATIONS" / "README.md", content)


def main() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required to generate the manual QA media fixture")

    shutil.rmtree(FIXTURE_ROOT, ignore_errors=True)
    (FIXTURE_ROOT / "00_README_EXPECTATIONS").mkdir(parents=True, exist_ok=True)

    created: list[CreatedFile] = []
    _scenario_01(created)
    _scenario_02(created)
    _scenario_03(created)
    _scenario_04(created)
    _scenario_05(created)
    _scenario_06(created)
    _scenario_07(created)
    _write_manifest(created)
    _write_expectations_readme()


if __name__ == "__main__":
    main()
