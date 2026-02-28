
# **Media Manager Dev Chat Backup**

## **1️⃣ Feature Branch Roadmaps**

### **Metadata-Enrichment Commit Roadmap**

1. **Initialize SQLite & scan skeleton**

   ```
   Initialize database and folder scan framework
   ```

   * SQLite connection & `files` table
   * Recursive folder scan (Windows-safe paths)
   * Register files in DB, skip enrichment

2. **Add image metadata extraction**

   ```
   Extract width, height, format, and EXIF datetime for images
   ```

   * Pillow extraction (JPEG/PNG/etc.)
   * Store in DB
   * Update `is_metadata_extracted` flag

3. **Add video/audio metadata extraction**

   ```
   Add video/audio metadata extraction using ffprobe
   ```

   * Extract duration, codec, bitrate, width/height
   * Store in DB
   * Update `is_metadata_extracted` flag
   * **Note:** Missing audio `channels` and `sample_rate`

4. **Make process resumable**

   ```
   Skip already enriched files for resumable processing
   ```

   * Check `is_metadata_extracted` before processing

5. **Optional: CLI & logging**

   ```
   Add simple CLI and logging for metadata enrichment
   ```

   * User-specified folder
   * Progress logging
   * Clean exits and error handling

---

### **Duplicate Detection Feature Roadmap**

Branch: `feature/duplicate-detection`

1. **Initialize framework & DB table**

   ```
   chore: create duplicate_candidates table and detection framework
   ```

   * Table: `duplicate_candidates(file_id_1, file_id_2, match_type, confidence_score)`

2. **Exact duplicates**

   ```
   feat: add exact duplicate detection using full file hashes
   ```

   * 100% confidence for identical file hashes

3. **Probable duplicates**

   ```
   feat: implement probable duplicate scoring using metadata heuristics
   ```

   * Criteria: size, duration, width/height, codec
   * Confidence score < 100%

4. **CLI & reporting**

   ```
   feat: add CLI to run duplicate detection and print results
   ```

---

## **2️⃣ Critical Commit Statements**

### Senior Dev Improvements

```
chore: enhance type safety, error handling, and code clarity in metadata extraction
```

### Performance Improvements

```
perf: batch DB updates and optimize file processing for speed
```

### Pylance / Type Fixes

```
fix: enforce full typing for JSON and metadata to satisfy Pylance
fix: add type hints and clarify variables to satisfy Pylance
```

### Scope Alignment Before Next Feature

```
chore: clarify metadata enrichment status and scope for video/audio
```

---

## **3️⃣ GitFlow / Branching Notes**

* `feature/metadata-enrichment` → complete → merge into `develop`

* `feature/duplicate-detection` → in progress → merge into `develop` when stable

* `master` updated **only on release**

* Typical workflow:

  ```bash
  git checkout develop
  git merge --no-ff feature/metadata-enrichment
  git push backup develop
  git checkout -b feature/duplicate-detection
  ```

* For releases:

  ```bash
  git checkout -b release/1.0.0 develop
  git merge --no-ff release/1.0.0 master
  git push backup master
  git checkout develop
  git merge --no-ff master
  ```

---

## **4️⃣ Project / Code Structure Recommendations**

```
media-manager/
│
├─ .venv/                     ← ignored by Git
├─ .gitignore
├─ media_manager/             ← core Python package
│   ├─ __init__.py
│   ├─ db.py                  ← SQLite helpers
│   ├─ metadata.py            ← metadata extraction
│   ├─ hashing.py             ← file hashing
│   ├─ scanner.py             ← folder scanning
│   └─ utils.py               ← path normalization, logging
│
├─ tests/                     ← unit tests
│   └─ test_metadata.py
├─ media-manager.db           ← database
├─ media-manager.sql          ← schema / migration
├─ requirements.txt
└─ main.py                    ← CLI entry point
```

* `.gitignore` recommendations:

```
__pycache__/
*.pyc
*.pyo
.venv/
media-manager.db
*.log
.vscode/
.idea/
*.iml
```

---

## **5️⃣ Code Snippets / Skeletons**

### Pillow Image Metadata Extraction

```python
from PIL import Image, ExifTags

def extract_image_metadata(path):
    try:
        with Image.open(path) as img:
            width, height = img.size
            format_ = img.format
            exif_datetime = None
            exif = getattr(img, "_getexif", lambda: None)() or {}
            for tag, val in exif.items():
                tag_name = ExifTags.TAGS.get(tag)
                if tag_name == "DateTime":
                    exif_datetime = val
                    break
            return {"width": width, "height": height, "format": format_, "exif_datetime": exif_datetime}
    except Exception:
        return None
```

### ffprobe Video/Audio Extraction

```python
import subprocess, json

def extract_media_metadata_ffprobe(path):
    cmd = ["ffprobe","-v","error","-print_format","json","-show_streams","-show_format", str(path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        fmt = data.get("format",{})
        duration = float(fmt.get("duration",0))
        bitrate = int(fmt.get("bit_rate",0))
        streams = data.get("streams",[])
        video = next((s for s in streams if s.get("codec_type")=="video"),{})
        audio = next((s for s in streams if s.get("codec_type")=="audio"),{})
        width = video.get("width")
        height = video.get("height")
        codec = video.get("codec_name") or audio.get("codec_name")
        channels = audio.get("channels")
        sample_rate = audio.get("sample_rate")
        return {"duration":duration,"bitrate":bitrate,"width":width,"height":height,"codec":codec,"channels":channels,"sample_rate":sample_rate}
    except Exception:
        return None
```

### Resumable Scan Skeleton

```python
def process_file(path: Path):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT is_metadata_extracted FROM files WHERE path=?", (str(path),))
    row = c.fetchone()
    if row and row[0]==1: return
    # determine media type
    # extract metadata
    # insert/update DB
    conn.commit()
    conn.close()
```

---

## **6️⃣ Notes / Recommendations**

* Don’t add channels/sample_rate yet — focus on duplicates first
* Always commit in **small functional increments**
* Push to `backup` frequently
* Keep `develop` stable; update `master` only on releases

---

This file contains **everything critical** from this conversation and can be safely saved and referenced later.

