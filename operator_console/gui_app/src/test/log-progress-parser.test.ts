import { describe, expect, it } from "vitest";

import { getLogLineTone, mergeLogLines, parseProgressLogs } from "@/lib/logs/parseProgressLogs";

describe("parseProgressLogs", () => {
  it("extracts structured ingest progress fields", () => {
    const result = parseProgressLogs([
      "2026-03-21 INFO media_manager.app.persistence.ingest phase=ingest stage=scan action=PROGRESS processed_count=100 total_count=285 progress_percent=35.1 throughput_fps=120.0 Progress: 100/285 files (35.1%) | 120.0 files/sec | elapsed 4.2s",
    ]);

    expect(result.phase).toBe("ingest");
    expect(result.stage).toBe("scan");
    expect(result.processedCount).toBe(100);
    expect(result.totalCount).toBe(285);
    expect(result.progressPercent).toBe(35.1);
    expect(result.throughputFps).toBe(120);
    expect(result.status).toBe("running");
  });

  it("prefers the newest active plan progress when both phases are present", () => {
    const result = parseProgressLogs([
      "2026-03-21 INFO media_manager.app.persistence.ingest phase=ingest action=PROGRESS processed_count=100 total_count=285 progress_percent=35.1 throughput_fps=120.0 Progress: 100/285 files (35.1%) | 120.0 files/sec | elapsed 4.2s",
      "2026-03-21 INFO media_manager.app.persistence.planner phase=plan stage=action_generation processed_count=50 total_count=80 progress_percent=62.5 throughput_fps=44.0 Progress: 50/80 files (62.5%) | 44.0 files/sec | elapsed 1.1s",
    ]);

    expect(result.phase).toBe("plan");
    expect(result.stage).toBe("action_generation");
    expect(result.processedCount).toBe(50);
    expect(result.totalCount).toBe(80);
  });

  it("uses the newest completion line instead of an older active progress line", () => {
    const result = parseProgressLogs([
      "2026-03-21 INFO media_manager.app.persistence.ingest phase=ingest action=PROGRESS processed_count=2800 total_count=2850 progress_percent=98.2 throughput_fps=28.2 Progress: 2800/2850 files (98.2%) | 28.2 files/sec | elapsed 99.2s",
      "2026-03-21 INFO media_manager.app.persistence.ingest phase=ingest action=PROGRESS processed_count=2850 total_count=2850 progress_percent=100.0 throughput_fps=28.2 Progress: 2850/2850 files (100.0%) | 28.2 files/sec | elapsed 101.1s",
    ]);

    expect(result.phase).toBe("ingest");
    expect(result.processedCount).toBe(2850);
    expect(result.totalCount).toBe(2850);
    expect(result.progressPercent).toBe(100);
    expect(result.status).toBe("idle");
  });

  it("maps apply, canonical, and tag enrichment phases with stage-aware parsing", () => {
    const applyResult = parseProgressLogs([
      "2026-03-21 INFO media_manager.app.persistence.apply phase=apply stage=execute_actions processed_count=100 total_count=120 progress_percent=83.3 throughput_fps=40.0 Progress: 100/120 items (83.3%) | 40.0 items/sec | elapsed 2.5s",
    ]);
    const canonicalResult = parseProgressLogs([
      "2026-03-21 INFO media_manager.app.persistence.canonicalization phase=canonical stage=recompute processed_count=1 total_count=1 progress_percent=100.0 throughput_fps=5.0 Progress: 1/1 items (100.0%) | 5.0 items/sec | elapsed 0.2s",
    ]);
    const tagResult = parseProgressLogs([
      "2026-03-21 INFO media_manager.app.persistence.tag_enrichment phase=tag_enrichment stage=enrich processed_count=2 total_count=5 progress_percent=40.0 throughput_fps=10.0 Progress: 2/5 items (40.0%) | 10.0 items/sec | elapsed 0.2s",
    ]);
    const integrityResult = parseProgressLogs([
      "2026-03-21 INFO media_manager.app.persistence.integrity phase=integrity stage=scan_active_files processed_count=4 total_count=10 progress_percent=40.0 throughput_fps=2.0 Progress: 4/10 files (40.0%) | 2.0 files/sec | elapsed 2.0s",
    ]);

    expect(applyResult.phase).toBe("apply");
    expect(applyResult.stage).toBe("execute_actions");
    expect(canonicalResult.phase).toBe("canonical");
    expect(canonicalResult.stage).toBe("recompute");
    expect(tagResult.phase).toBe("tag");
    expect(tagResult.stage).toBe("enrich");
    expect(integrityResult.phase).toBe("integrity");
    expect(integrityResult.stage).toBe("scan_active_files");
  });

  it("marks warning and error lines for highlighting", () => {
    expect(getLogLineTone("2026-03-21 WARNING planner something odd")).toBe("warning");
    expect(getLogLineTone("2026-03-21 ERROR planner failed badly")).toBe("error");
    expect(getLogLineTone("2026-03-21 INFO normal progress")).toBe("default");
  });

  it("merges overlapping log snapshots without duplicating lines", () => {
    const merged = mergeLogLines(["line-1", "line-2"], ["line-2", "line-3"]);

    expect(merged).toEqual(["line-1", "line-2", "line-3"]);
  });
});
