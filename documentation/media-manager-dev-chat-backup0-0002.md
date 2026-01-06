├─ [Commit 1] Initialize database and scan skeleton
│    └─ SQLite connection + files table
│    └─ Recursive folder scan, Windows-safe paths
│    └─ Register files, skip enrichment
│
├─ [Commit 2] Extract width, height, format, and EXIF datetime for images
│    └─ Pillow extraction for JPEG/PNG/etc.
│    └─ Store in DB
│    └─ Update is_metadata_extracted flag
│
├─ [Commit 3] Add video/audio metadata extraction using ffprobe
│    └─ Extract duration, codec, bitrate, width/height, channels/sample rate
│    └─ Store in DB
│    └─ Update is_metadata_extracted flag
│
├─ [Commit 4] Skip already enriched files for resumable processing
│    └─ Check is_metadata_extracted before processing
│    └─ Works for images, video, audio
│    └─ Test on partially enriched folders
│
└─ [Commit 5] Add simple CLI and logging for metadata enrichment (optional)
     └─ main.py entry point, user-specified folder
     └─ Print/log progress
     └─ Ensure clean exits & error handling
	 

Let's go back to this:

Great! Let’s make this **minimal commit roadmap** for your `feature/metadata-enrichment` feature. It’s structured so you can make **steady progress** without getting stuck in refactoring too early.

---

## **Feature Commit Plan: `metadata-enrichment`**

1. **Initialize SQLite & scan skeleton**

   * Commit message:

     ```
     Initialize database and folder scan framework
     ```
   * What to do:

     * Create SQLite connection & `files` table
     * Add basic folder scanning logic (recursive, Windows-safe paths)
     * Skip enrichment for now, just register files in DB

---

2. **Add image metadata extraction**

   * Commit message:

     ```
     Extract width, height, format, and EXIF datetime for images
     ```
   * What to do:

     * Use Pillow for JPEG/PNG/etc.
     * Store results in DB
     * Update `is_metadata_extracted` flag for images

---

3. **Add video/audio metadata extraction**

   * Commit message:

     ```
     Add video/audio metadata extraction using ffprobe
     ```
   * What to do:

     * Extract duration, codec, bitrate, width/height, channels/sample rate
     * Store results in DB
     * Update `is_metadata_extracted` flag

---

4. **Make process resumable**

   * Commit message:

     ```
     Skip already enriched files for resumable processing
     ```
   * What to do:

     * Modify scan logic to check `is_metadata_extracted` before processing
     * Ensure it works for images, video, audio
     * Test on partially enriched folders

---

5. **Optional: CLI & logging**

   * Commit message:

     ```
     Add simple CLI and logging for metadata enrichment
     ```
   * What to do:

     * Add `main.py` entry point: user specifies folder
     * Print/log progress: processed vs skipped files
     * Ensure clean exits & error handling

---

### **Notes**

* Each commit should be **small and functional**
* Test each step before committing
* Push regularly to your local backup:

```bash
git push backup feature/metadata-enrichment
```

---

If you follow this, by the end you’ll have a **fully functional, resumable metadata enrichment feature**, all tracked under GitFlow, and you can refactor into a modular package later without losing any progress.

I can also sketch a **visual “commit checkpoint map”** showing these 5 steps — it makes the roadmap super easy to follow. Do you want me to do that?
	 