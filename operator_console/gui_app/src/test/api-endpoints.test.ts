import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/client", () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

import { apiGet, apiPost } from "@/lib/api/client";
import {
  adminDbReset,
  getDuplicateBinPolicy,
  getDuplicateBinItems,
  getDirectoryPickerCapability,
  getDirectoryPickerListing,
  getIntegrityDashboard,
  moveDuplicatesToBin,
  reportIntegrityPlaybackFailure,
  restoreDuplicatesFromBin,
  runIntegrityScan,
  runIngest,
  setDuplicateReclaim,
  updatePolicy,
} from "@/lib/api/endpoints";

describe("api endpoints", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("uses canonical folder_path for ingest requests", async () => {
    vi.mocked(apiPost).mockResolvedValue({
      ok: true,
      workflow_version: "v2-service-layer",
      schema_version: "schema-1",
      generated_at: "2026-03-14T00:00:00+00:00",
      data: {
        operation: "INGEST",
        mode: "VALIDATION_ONLY",
      },
      errors: [],
    });

    await runIngest({ folder_path: "/dataset", dry_run: true });

    expect(apiPost).toHaveBeenCalledWith("/ingest", {
      folder_path: "/dataset",
      dry_run: true,
    });
  });

  it("maps fallback operation names and duration for tag enrichment responses", async () => {
    vi.mocked(apiPost).mockResolvedValue({
      ok: true,
      workflow_version: "v2-service-layer",
      schema_version: "schema-1",
      generated_at: "2026-03-16T00:00:00+00:00",
      data: {
        status: "COMPLETED",
        duration_ms: 926,
        operation_run_id: "op-run-1",
        number_of_items_processed: 72,
      },
      errors: [],
    });

    const { data } = await import("@/lib/api/endpoints").then((mod) =>
      mod.runTagEnrichment({ all: true, batch_size: 100, source: "system" }),
    );

    expect(data.operation).toBe("TAG_ENRICHMENT");
    expect(data.summary).toBe("Tag Enrichment completed.");
    expect(data.duration_ms).toBe(926);
  });

  it("uses challenge_word for admin reset requests", async () => {
    vi.mocked(apiPost).mockResolvedValue({
      ok: true,
      workflow_version: "v2-service-layer",
      schema_version: "schema-1",
      generated_at: "2026-03-14T00:00:00+00:00",
      data: {
        success: true,
      },
      errors: [],
    });

    await adminDbReset({ dry_run: false, challenge_word: "media-manager" });

    expect(apiPost).toHaveBeenCalledWith("/admin/db-reset", {
      dry_run: false,
      challenge_word: "media-manager",
    });
  });

  it("derives canonical policy update payloads through the API client only", async () => {
    vi.mocked(apiGet).mockResolvedValue({
      ok: true,
      workflow_version: "v2-service-layer",
      schema_version: "schema-1",
      generated_at: "2026-03-14T00:00:00+00:00",
      data: {
        canonical_priority: {
          selected_policy: "FIRST_SEEN",
          preferred_roots: ["/media"],
        },
        naming: {
          strategy: "SHARED_CANONICAL_NAME",
        },
        integrity: {
          default_scan_mode: "FAST",
          issue_min_confidence: 0.9,
          notify_on_high_confidence: true,
        },
        duplicate_reclaim: {
          archive_root: "/tmp/media-manager/reclaim",
          default_retention_days: 14,
          notify_on_reviewed_safe: true,
        },
        retention: {
          quarantine_root: "/tmp/media-manager/quarantine",
          recycle_bin_root: "/tmp/media-manager/recycle-bin",
          quarantine_retention_days: 14,
          recycle_purge_days: 30,
        },
        automation: {
          mode: "NOTIFY_ONLY",
        },
        recanonicalization: {
          enabled: true,
        },
        metadata: {
          version: 7,
          updated_at: null,
        },
      },
      errors: [],
    });
    vi.mocked(apiPost).mockResolvedValue({
      ok: true,
      workflow_version: "v2-service-layer",
      schema_version: "schema-1",
      generated_at: "2026-03-14T00:00:00+00:00",
      data: {
        canonical_priority: {
          selected_policy: "PREFER_ROOT",
          preferred_roots: ["/archive"],
        },
        naming: {
          strategy: "DUPLICATE_OWNS_DATE_STANDARDIZED",
        },
        integrity: {
          default_scan_mode: "FAST",
          issue_min_confidence: 0.9,
          notify_on_high_confidence: true,
        },
        duplicate_reclaim: {
          archive_root: "/tmp/media-manager/reclaim",
          default_retention_days: 14,
          notify_on_reviewed_safe: true,
        },
        retention: {
          quarantine_root: "/tmp/media-manager/quarantine",
          recycle_bin_root: "/tmp/media-manager/recycle-bin",
          quarantine_retention_days: 14,
          recycle_purge_days: 30,
        },
        automation: {
          mode: "NOTIFY_ONLY",
        },
        recanonicalization: {
          enabled: false,
        },
        metadata: {
          version: 8,
          updated_at: null,
        },
      },
      errors: [],
    });

    await updatePolicy({
      selected_policy: "PREFER_ROOT",
      naming_strategy: "DUPLICATE_OWNS_DATE_STANDARDIZED",
      preferred_roots: ["/archive"],
      recanonicalization_enabled: false,
    });

    expect(apiGet).toHaveBeenCalledWith("/policy");
    expect(apiPost).toHaveBeenCalledWith("/policy", {
      selected_policy: "PREFER_ROOT",
      naming_strategy: "DUPLICATE_OWNS_DATE_STANDARDIZED",
      preferred_roots: ["/archive"],
      integrity_scan_default_mode: "FAST",
      integrity_issue_min_confidence: 0.9,
      integrity_notify_on_high_confidence: true,
      duplicate_reclaim_archive_root: "/tmp/media-manager/reclaim",
      duplicate_reclaim_default_retention_days: 14,
      duplicate_reclaim_notify_on_reviewed_safe: true,
      integrity_quarantine_root: "/tmp/media-manager/quarantine",
      integrity_quarantine_retention_days: 14,
      recycle_bin_root: "/tmp/media-manager/recycle-bin",
      recycle_purge_days: 30,
      automation_mode: "NOTIFY_ONLY",
      recanonicalization_enabled: false,
      version: 7,
    });
  });

  it("loads directory picker capability through the API client only", async () => {
    vi.mocked(apiGet).mockResolvedValue({
      ok: true,
      workflow_version: "v2-service-layer",
      schema_version: "schema-1",
      generated_at: "2026-03-14T00:00:00+00:00",
      data: {
        enabled: true,
        roots: [{ label: "incoming", path: "/srv/media/incoming" }],
      },
      errors: [],
    });

    await getDirectoryPickerCapability();

    expect(apiGet).toHaveBeenCalledWith("/directory-picker/capability");
  });

  it("loads duplicate bin policy through the API client only", async () => {
    vi.mocked(apiGet).mockResolvedValue({
      ok: true,
      workflow_version: "v2-service-layer",
      schema_version: "schema-1",
      generated_at: "2026-03-29T00:00:00+00:00",
      data: {
        current_move_root: "/tmp/media-manager/recycle-bin",
        current_retention_days: 14,
        target_recycle_bin_root: "/tmp/media-manager/recycle-bin",
        implementation: "reclaim_compatibility",
      },
      errors: [],
    });

    await getDuplicateBinPolicy();

    expect(apiGet).toHaveBeenCalledWith("/duplicates/bin-policy");
  });

  it("loads directory picker listings through the API client only", async () => {
    vi.mocked(apiGet).mockResolvedValue({
      ok: true,
      workflow_version: "v2-service-layer",
      schema_version: "schema-1",
      generated_at: "2026-03-14T00:00:00+00:00",
      data: {
        current_path: "/srv/media/incoming",
        parent_path: "/srv/media",
        directories: [{ name: "album-a", path: "/srv/media/incoming/album-a" }],
      },
      errors: [],
    });

    await getDirectoryPickerListing("/srv/media/incoming");

    expect(apiGet).toHaveBeenCalledWith("/directory-picker/list", {
      path: "/srv/media/incoming",
    });
  });

  it("routes integrity dashboard reads through the API client", async () => {
    vi.mocked(apiGet).mockResolvedValue({
      ok: true,
      workflow_version: "v2-service-layer",
      schema_version: "schema-1",
      generated_at: "2026-03-25T00:00:00+00:00",
      data: {
        total_files_scanned: 12,
        playback_issues: 3,
      },
      errors: [],
    });

    await getIntegrityDashboard();

    expect(apiGet).toHaveBeenCalledWith("/integrity/dashboard");
  });

  it("posts duplicate reclaim readiness through the API client", async () => {
    vi.mocked(apiPost).mockResolvedValue({
      ok: true,
      workflow_version: "v2-service-layer",
      schema_version: "schema-1",
      generated_at: "2026-03-25T00:00:00+00:00",
      data: { reclaim_status: "REVIEWED_SAFE_TO_RECLAIM" },
      errors: [],
    });

    await setDuplicateReclaim({
      content_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      reclaim_status: "REVIEWED_SAFE_TO_RECLAIM",
    });

    expect(apiPost).toHaveBeenCalledWith("/duplicates/reclaim", {
      content_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      reclaim_status: "REVIEWED_SAFE_TO_RECLAIM",
    });
  });

  it("loads duplicate bin items through the existing reclaim-shaped route", async () => {
    vi.mocked(apiGet).mockResolvedValue({
      ok: true,
      workflow_version: "v2-service-layer",
      schema_version: "schema-1",
      generated_at: "2026-04-01T00:00:00+00:00",
      data: {
        total_count: 75,
        page: 2,
        limit: 50,
        total_pages: 2,
        items: [],
      },
      errors: [],
    });

    await getDuplicateBinItems({ page: 2, limit: 50 });

    expect(apiGet).toHaveBeenCalledWith("/duplicates/reclaim/items", {
      page: 2,
      limit: 50,
    });
  });

  it("moves duplicate groups to the bin through the existing reclaim-shaped route", async () => {
    vi.mocked(apiPost).mockResolvedValue({
      ok: true,
      workflow_version: "v2-service-layer",
      schema_version: "schema-1",
      generated_at: "2026-04-01T00:00:00+00:00",
      data: { summary: { applied_count: 3 } },
      errors: [],
    });

    await moveDuplicatesToBin({
      content_ids: ["group-alpha", "group-beta"],
      retention_days: 21,
    });

    expect(apiPost).toHaveBeenCalledWith("/duplicates/reclaim/execute", {
      content_ids: ["group-alpha", "group-beta"],
      retention_days: 21,
    });
  });

  it("restores duplicate files from the bin through the existing reclaim-shaped route", async () => {
    vi.mocked(apiPost).mockResolvedValue({
      ok: true,
      workflow_version: "v2-service-layer",
      schema_version: "schema-1",
      generated_at: "2026-04-01T00:00:00+00:00",
      data: { summary: { applied_count: 1 } },
      errors: [],
    });

    await restoreDuplicatesFromBin({
      file_instance_ids: ["aaaaaaaa-0000-0000-0000-000000000010"],
    });

    expect(apiPost).toHaveBeenCalledWith("/duplicates/reclaim/restore", {
      file_instance_ids: ["aaaaaaaa-0000-0000-0000-000000000010"],
    });
  });

  it("posts integrity scans through the operations client surface", async () => {
    vi.mocked(apiPost).mockResolvedValue({
      ok: true,
      workflow_version: "v2-service-layer",
      schema_version: "schema-1",
      generated_at: "2026-03-25T00:00:00+00:00",
      data: { scan_mode: "DEEP", scanned_count: 10 },
      errors: [],
    });

    await runIntegrityScan({ mode: "DEEP", file_instance_ids: [] });

    expect(apiPost).toHaveBeenCalledWith("/integrity/scan", {
      mode: "DEEP",
      file_instance_ids: [],
    });
  });

  it("posts playback failure scans through the media client surface", async () => {
    vi.mocked(apiPost).mockResolvedValue({
      ok: true,
      workflow_version: "v2-service-layer",
      schema_version: "schema-1",
      generated_at: "2026-03-25T00:00:00+00:00",
      data: { trigger: "playback_failure" },
      errors: [],
    });

    await reportIntegrityPlaybackFailure({
      file_instance_id: "aaaaaaaa-0000-0000-0000-000000000002",
    });

    expect(apiPost).toHaveBeenCalledWith("/integrity/playback-failure", {
      file_instance_id: "aaaaaaaa-0000-0000-0000-000000000002",
    });
  });
});
