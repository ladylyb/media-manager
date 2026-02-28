# Media Manager Filename & Metadata Requirements

## Filename Requirements

The filename **must include all core identifiers** for readability, portability, and chronological sorting. Use the following pattern:

```
[Type]_[YYYYMMDD]_[HHMMSS]_[Owner/Source]_[Context].[ext]
```

**Elements:**

| Element      | Description                                              | Allowed Values / Format                           | Example                   |
| ------------ | -------------------------------------------------------- | ------------------------------------------------- | ------------------------- |
| Type         | Media type                                               | `IMG` = image, `VID` = video                      | `IMG`, `VID`              |
| Date         | Creation/taken date                                      | `YYYYMMDD` (year-month-day)                       | `20210913`                |
| Time         | Optional; ensures uniqueness                             | `HHMMSS` (hour-minute-second, 24h)                | `105408`                  |
| Owner/Source | Indicates origin                                         | `LL` = personal (ladylyb), `TP` = third-party     | `LL`, `TP`                |
| Context/Tag  | Optional short descriptor (event, chapter, content type) | Alphanumeric, underscores allowed, <20 characters | `Birthday`, `Ch1`, `Trip` |

**Examples:**

* Personal Image: `IMG_20210913_105408_LL_Beach.JPG`
* Personal Video: `VID_20200330_100451_LL_Family.mp4`
* Third-Party Image: `IMG_20211201_120500_TP_Clipart.jpg`
* Third-Party Video: `VID_20211120_081230_TP_Funny.mp4`

---

## Metadata Requirements

All other descriptive or technical information should be captured as **metadata** fields:

| Metadata Field                  | Description / Purpose                                    |
| ------------------------------- | -------------------------------------------------------- |
| Title                           | Optional descriptive title                               |
| Description                     | Long-form notes, story, or context                       |
| Tags                            | Multiple tags for event, mood, chapter, people, location |
| Camera / Device Info            | Extracted from EXIF or file properties                   |
| File Size, Resolution, Duration | Standard media info                                      |
| Location / GPS                  | If available                                             |
| Original Source / URL           | For third-party content                                  |

**Notes:**

* Owner/Source and Context **must always appear in the filename** even if metadata exists.
* Date/Time should ideally be synced with file creation timestamp; fallback to filename if missing.
* Duplicate detection can be handled via timestamp + optional hash.
* Context tags can include chapters (`Ch1`) or short descriptive keywords.

---

## Optional Enhancements

* Auto-suggest tags based on EXIF, location, or filename keywords.
* Ensure filenames are sortable chronologically by keeping `YYYYMMDD_HHMMSS` at the front.
* Chapters or personal journaling markers (`Ch1`, `Ch2`) are optional but supported in the context field.

