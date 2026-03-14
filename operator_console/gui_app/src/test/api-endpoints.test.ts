import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/client", () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

import { apiGet, apiPost } from "@/lib/api/client";
import { adminDbReset, runIngest, updatePolicy } from "@/lib/api/endpoints";

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
        preferred_roots: ["/archive"],
        recanonicalization_enabled: false,
        version: 8,
      },
      errors: [],
    });

    await updatePolicy({
      selected_policy: "PREFER_ROOT",
      preferred_roots: ["/archive"],
      recanonicalization_enabled: false,
    });

    expect(apiGet).toHaveBeenCalledWith("/policy");
    expect(apiPost).toHaveBeenCalledWith("/policy", {
      selected_policy: "PREFER_ROOT",
      preferred_roots: ["/archive"],
      recanonicalization_enabled: false,
      version: 7,
    });
  });
});
