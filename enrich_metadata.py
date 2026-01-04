from typing import Optional, Literal, TypedDict, Any, List, Tuple
from pathlib import Path
import sqlite3
import os
from PIL import Image, ExifTags
import subprocess
import json

DB_PATH = Path("media-manager.db")

# -------------------- TYPEDDICT DEFINITIONS --------------------
class MediaMetadata(TypedDict, total=False):
    media_type: Literal["image", "video", "audio", "other"]
    width: Optional[int]
    height: Optional[int]
    duration: Optional[float]
    codec: Optional[str]
    bitrate: Optional[int]
    exif_datetime: Optional[str]

# -------------------- IMAGE METADATA --------------------
def get_image_metadata(file_path: Path) -> MediaMetadata:
    try:
        with Image.open(file_path) as img:
            width, height = img.size
            exif_data: Optional[dict[int, Any]] = getattr(img, "_getexif", lambda: None)()
            exif_datetime: Optional[str] = None
            if exif_data:
                for tag, value in exif_data.items():
                    tag_name = ExifTags.TAGS.get(tag, tag)
                    if tag_name == "DateTimeOriginal":
                        exif_datetime = str(value)
                        break
            return MediaMetadata(
                width=width,
                height=height,
                exif_datetime=exif_datetime,
                media_type="image"
            )
    except Exception as e:
        print(f"Warning: failed to read image metadata for {file_path}: {e}")
        return MediaMetadata(media_type="image")

# -------------------- VIDEO/AUDIO METADATA --------------------
def get_media_metadata(file_path: Path) -> MediaMetadata:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        str(file_path)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data: dict[str, Any] = json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"Warning: ffprobe failed for {file_path}: {e}")
        return MediaMetadata(media_type="other")

    fmt: dict[str, Any] = data.get("format", {})
    duration: Optional[float] = float(fmt["duration"]) if "duration" in fmt else None
    bitrate: Optional[int] = int(fmt["bit_rate"]) if "bit_rate" in fmt else None

    streams: List[dict[str, Any]] = data.get("streams", [])
    width: Optional[int] = None
    height: Optional[int] = None
    codec: Optional[str] = None
    media_type: Literal["video", "audio", "other"] = "audio"

    if streams:
        first_stream: dict[str, Any] = streams[0]
        codec = first_stream.get("codec_name")
        width = first_stream.get("width")
        height = first_stream.get("height")
        if width is not None and height is not None:
            media_type = "video"

    return MediaMetadata(
        duration=duration,
        width=width,
        height=height,
        codec=codec,
        bitrate=bitrate,
        media_type=media_type
    )

# -------------------- MAIN FUNCTION --------------------
def main(batch_size: int = 50) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    cur = conn.cursor()

    cur.execute("SELECT id, path FROM files WHERE is_metadata_extracted = 0")
    rows: List[Tuple[int, str]] = cur.fetchall()
    print(f"{len(rows)} files to enrich")

    # Explicitly typed list of update tuples
    updates: List[Tuple[
        Optional[str], Optional[float], Optional[int], Optional[int],
        Optional[str], Optional[int], Optional[str], int
    ]] = []

    for idx, (file_id, path_str) in enumerate(rows, start=1):
        file_path = Path(os.path.normpath(path_str))
        if not file_path.exists():
            print(f"Skipping missing file: {file_path}")
            continue

        suffix = file_path.suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}:
            metadata: MediaMetadata = get_image_metadata(file_path)
        elif suffix in {".mp4", ".mkv", ".avi", ".mov", ".mp3", ".wav", ".flac"}:
            metadata: MediaMetadata = get_media_metadata(file_path)
        else:
            metadata = MediaMetadata(media_type="other")

        # Append with fully typed tuple
        updates.append((
            metadata.get("media_type"),
            metadata.get("duration"),
            metadata.get("width"),
            metadata.get("height"),
            metadata.get("codec"),
            metadata.get("bitrate"),
            metadata.get("exif_datetime"),
            file_id
        ))

        if idx % batch_size == 0 or idx == len(rows):
            cur.executemany("""
                UPDATE files SET
                    media_type = ?,
                    duration = ?,
                    width = ?,
                    height = ?,
                    codec = ?,
                    bitrate = ?,
                    exif_datetime = ?,
                    is_metadata_extracted = 1
                WHERE id = ?
            """, updates)
            conn.commit()
            updates.clear()
            print(f"Processed {idx}/{len(rows)} files")

    conn.close()
    print("Metadata enrichment complete")

if __name__ == "__main__":
    main()
