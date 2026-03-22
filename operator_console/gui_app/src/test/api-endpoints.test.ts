import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/client", () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

import { apiGet, apiPost } from "@/lib/api/client";
import {
  adminDbReset,
  getDirectoryPickerCapability,
  getDirectoryPickerListing,
  runIngest,
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
        selected_policy: "FIRST_SEEN",
        naming_strategy: "SHARED_CANONICAL_NAME",
        preferred_roots: ["/media"],
        recanonicalization_enabled: true,
        version: 7,
      },
      errors: [],
    });
    vi.mocked(apiPost).mockResolvedValue({
      ok: true,
      workflow_version: "v2-service-layer",
      schema_version: "schema-1",
      generated_at: "2026-03-14T00:00:00+00:00",
      data: {
        selected_policy: "PREFER_ROOT",
        naming_strategy: "DUPLICATE_OWNS_DATE_STANDARDIZED",
        preferred_roots: ["/archive"],
        recanonicalization_enabled: false,
        version: 8,
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
});
