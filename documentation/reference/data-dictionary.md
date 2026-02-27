# Media Manager Data Dictionary

## High-level model (how the pieces fit)

scans → files → (duplicate_candidates, file_actions)

* A **scan** represents one execution over a root directory.
* A **file** is a discovered media object during a scan.
* **duplicate_candidates** records *relationships* between two files with a scoring rationale.
* **file_actions** records *decisions* taken on individual files (move, delete, keep, etc.).
* `_file_actions_old` is a legacy table preserved for migration/history.

---

## Table-by-table data dictionary

### 1. `scans`

Represents a single filesystem crawl / ingestion run.

| Column        | Type            | Description                                                 |
| ------------- | --------------- | ----------------------------------------------------------- |
| `id`          | INTEGER (PK)    | Unique scan identifier                                      |
| `root_path`   | TEXT (NOT NULL) | Root directory scanned                                      |
| `started_at`  | DATETIME        | Timestamp when scan started (defaults to CURRENT_TIMESTAMP) |
| `finished_at` | DATETIME        | Timestamp when scan completed                               |
| `notes`       | TEXT            | Free-form notes (errors, partial scans, comments)           |

**Intent:**
Acts as a *batch boundary* so files can be reasoned about in the context of a specific scan.

---

### 2. `files`

Canonical representation of a discovered media file.

| Column                  | Type                    | Description                     |
| ----------------------- | ----------------------- | ------------------------------- |
| `id`                    | INTEGER (PK)            | Internal file ID                |
| `scan_id`               | INTEGER (FK → scans.id) | Scan that discovered this file  |
| `path`                  | TEXT (NOT NULL)         | Directory path                  |
| `filename`              | TEXT (NOT NULL)         | File name without path          |
| `extension`             | TEXT                    | File extension                  |
| `size_bytes`            | INTEGER (NOT NULL)      | File size                       |
| `mtime`                 | REAL                    | Modified time (epoch/float)     |
| `ctime`                 | REAL                    | Created time                    |
| `hash_partial`          | TEXT                    | Fast / partial hash             |
| `hash_full`             | TEXT                    | Full-content hash               |
| `hash_algo`             | TEXT                    | Hash algorithm used             |
| `media_type`            | TEXT                    | image / video / audio / unknown |
| `duration`              | REAL                    | Duration (media only)           |
| `width`                 | INTEGER                 | Pixel width                     |
| `height`                | INTEGER                 | Pixel height                    |
| `codec`                 | TEXT                    | Codec information               |
| `bitrate`               | INTEGER                 | Bitrate                         |
| `exif_datetime`         | TEXT                    | EXIF capture time               |
| `camera_model`          | TEXT                    | Camera/device model             |
| `orientation`           | TEXT                    | EXIF orientation                |
| `is_hashed`             | INTEGER (0/1)           | Hash computation completed      |
| `is_metadata_extracted` | INTEGER (0/1)           | Metadata extraction completed   |

**Intent:**
This is the **core truth table**. Every deduplication, grouping, and action traces back here.

---

### 3. `duplicate_candidates`

Represents *suspected* duplicate relationships between two files.

| Column               | Type                    | Description                                       |
| -------------------- | ----------------------- | ------------------------------------------------- |
| `id`                 | INTEGER (PK)            | Candidate ID                                      |
| `file_id_1`          | INTEGER (FK → files.id) | First file                                        |
| `file_id_2`          | INTEGER (FK → files.id) | Second file                                       |
| `match_type`         | TEXT                    | e.g. exact_hash, partial_hash, metadata, filename |
| `confidence_score`   | INTEGER (NOT NULL)      | Heuristic confidence (project-defined scale)      |
| `reason`             | TEXT                    | Human-readable explanation                        |
| `duplicate_group_id` | INTEGER                 | Logical grouping of duplicates                    |
| `created_at`         | DATETIME                | When candidate was created                        |

Constraints

* `UNIQUE (file_id_1, file_id_2, match_type)`

Intent:
This is **evidence**, not a verdict. It supports:

* review workflows
* automated decisions
* grouping logic

---

### 4. `file_actions`

Authoritative record of decisions taken on files.

| Column        | Type                    | Description                          |
| ------------- | ----------------------- | ------------------------------------ |
| `id`          | INTEGER (PK)            | Action ID                            |
| `file_id`     | INTEGER (FK → files.id) | Target file                          |
| `action`      | TEXT (NOT NULL)         | keep / move / delete / archive / etc |
| `target_path` | TEXT                    | Destination path (if applicable)     |
| `decided_at`  | DATETIME                | When decision was made               |
| `notes`       | TEXT                    | Rationale or operator notes          |

Intent:
This is the **source of truth for side effects**.
Anything that actually changes the filesystem must be traceable here.

---

### 5. `_file_actions_old`

Legacy / transitional version of `file_actions`.

Same structure as `file_actions`, retained for:

* migration validation
* audit/history comparison
