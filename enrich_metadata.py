import sqlite3
import os
from pathlib import Path
from PIL import Image, ExifTags
import subprocess
import json
from typing import Any, Dict, Optional

DB_PATH = r"media-manager.db"

def get_image_metadata(file_path: str) -> Optional[Dict[str, Any]]:
    """Extract image metadata including width, height, and EXIF datetime."""
    try:
        with Image.open(file_path) as img:
            width, height = img.size
            exif_data: Optional[Dict[int, Any]] = img._getexif()  # type: ignore[attr-defined]
            exif_datetime: Optional[str] = None
            if exif_data:
                for tag, value in exif_data.items():
                    decoded = ExifTags.TAGS.get(tag, tag)
                    if decoded == "DateTimeOriginal":
                        exif_datetime = value
                        break
            return {
                "width": width,
                "height": height,
                "exif_datetime": exif_datetime,
                "media_type": "image"
            }
    except Exception:
        return None

def get_media_metadata(file_path: str) -> Optional[Dict[str, Any]]:
    """Use ffprobe to get video/audio metadata."""
    try:
        cmd: list[str] = [
            "ffprobe",
            "-v", "error",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        data: Dict[str, Any] = json.loads(result.stdout)
        duration: Optional[float] = None
        width: Optional[int] = None
        height: Optional[int] = None
        codec: Optional[str] = None
        bitrate: Optional[int] = None
        streams: list[Dict[str, Any]] = data.get("streams", [])
        if streams:
            stream = streams[0]
            codec = stream.get("codec_name")
            width = stream.get("width")
            height = stream.get("height")
        fmt: Dict[str, Any] = data.get("format", {})
        if fmt:
            duration = float(fmt.get("duration")) if fmt.get("duration") else None
            bitrate = int(fmt.get("bit_rate")) if fmt.get("bit_rate") else None
        return {
            "duration": duration,
            "width": width,
            "height": height,
            "codec": codec,
            "bitrate": bitrate,
            "media_type": "video" if streams and "width" in streams[0] else "audio"
        }
    except Exception:
        return None

def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    cur = conn.cursor()

    # Select files not yet enriched
    cur.execute("""
        SELECT id, path
        FROM files
        WHERE is_metadata_extracted = 0
    """)
    rows: list[tuple[int, str]] = cur.fetchall()
    print(f"{len(rows)} files to enrich")

    for idx, (file_id, file_path) in enumerate(rows, 1):
        file_path = os.path.normpath(file_path)
        path_obj = Path(file_path)
        metadata: Optional[Dict[str, Any]] = None

        if path_obj.suffix.lower() in [".jpg", ".jpeg", ".png", ".bmp", ".tiff"]:
            metadata = get_image_metadata(file_path)
        elif path_obj.suffix.lower() in [".mp4", ".mkv", ".avi", ".mov", ".mp3", ".wav", ".flac"]:
            metadata = get_media_metadata(file_path)
        else:
            metadata = {"media_type": "other"}

        if metadata:
            cur.execute("""
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
            """, (
                metadata.get("media_type"),
                metadata.get("duration"),
                metadata.get("width"),
                metadata.get("height"),
                metadata.get("codec"),
                metadata.get("bitrate"),
                metadata.get("exif_datetime"),
                file_id
            ))
            conn.commit()

        if idx % 20 == 0:
            print(f"Processed {idx}/{len(rows)} files")

    conn.close()
    print("Metadata enrichment complete")


if __name__ == "__main__":
    main()
