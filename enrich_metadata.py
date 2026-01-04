import sqlite3
import os
from pathlib import Path
from typing import Optional, Dict, Literal, List, Tuple
from PIL import Image, ExifTags
import subprocess
import json

DB_PATH = Path("media-manager.db")

# -------------------- TYPE DEFINITIONS --------------------
ImageMetadata = Dict[str, Optional[object]]
MediaMetadata = Dict[str, Optional[object]]
MediaType = Literal["image", "video", "audio", "other"]

# -------------------- IMAGE METADATA --------------------
def get_image_metadata(file_path: Path) -> Optional[ImageMetadata]:
    """Extract image metadata: width, height, exif datetime."""
    try:
        with Image.open(file_path) as img:
            width, height = img.size
            exif_data: Optional[Dict[int, object]] = getattr(img, "_getexif", lambda: None)()  # type: ignore
            exif_datetime: Optional[str] = None
            if exif_data:
                for tag, value in exif_data.items():
                    tag_name = ExifTags.TAGS.get(tag, tag)
                    if tag_name == "DateTimeOriginal":
                        exif_datetime = str(value)
                        break
            return {
                "width": width,
                "height": height,
                "exif_datetime": exif_datetime,
                "media_type": "image",
                "duration": None,
                "codec": None,
                "bitrate": None
            }
    except Exception as e:
        print(f"Warning: failed to read image metadata for {file_path}: {e}")
        return None

# -------------------- VIDEO/AUDIO METADATA --------------------
def get_media_metadata(file_path: Path) -> Optional[MediaMetadata]:
    """Extract video/audio metadata using ffprobe."""
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
        data: Dict[str, object] = json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"Warning: ffprobe failed for {file_path}: {e}")
        return None

    fmt = data.get("format", {})
    duration: Optional[float] = float(fmt["duration"]) if "duration" in fmt else None
    bitrate: Optional[int] = int(fmt["bit_rate"]) if "bit_rate" in fmt else None

    streams = data.get("streams", [])
    width: Optional[int] = None
    height: Optional[int] = None
    codec: Optional[str] = None
    media_type: MediaType = "audio"

    if streams:
        first_stream = streams[0]
        codec = first_stream.get("codec_name")
        width = first_stream.get("width")
        height = first_stream.get("height")
        if width is not None and height is not None:
            media_type = "video"

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "codec": codec,
        "bitrate": bitrate,
        "media_type": media_type,
        "exif_datetime": None
    }

# -------------------- MAIN FUNCTION --------------------
def main(batch_size: int = 50) -> None:
    """Main metadata enrichment, batching DB commits for efficiency."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    cur = conn.cursor()

    # Fetch files that need metadata extraction
    cur.execute("""
        SELECT id, path
        FROM files
        WHERE is_metadata_extracted = 0
    """)
    rows: List[Tuple[int, str]] = cur.fetchall()
    print(f"{len(rows)} files to enrich")

    updates: List[Tuple[Optional[str], Optional[float], Optional[int], Optional[int],
                        Optional[str], Optional[int], Optional[str], int]] = []

    for idx, (file_id, path_str) in enumerate(rows, start=1):
        file_path = Path(os.path.normpath(path_str))
        if not file_path.exists():
            print(f"Skipping missing file: {file_path}")
            continue

        suffix = file_path.suffix.lower()
        metadata: Optional[MediaMetadata] = None

        if suffix in {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}:
            metadata = get_image_metadata(file_path)
        elif suffix in {".mp4", ".mkv", ".avi", ".mov", ".mp3", ".wav", ".flac"}:
            metadata = get_media_metadata(file_path)
        else:
            metadata = {
                "media_type": "other",
                "width": None,
                "height": None,
                "duration": None,
                "codec": None,
                "bitrate": None,
                "exif_datetime": None
            }

        if metadata:
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

        # Commit batch
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

# -------------------- ENTRY POINT --------------------
if __name__ == "__main__":
    main()
