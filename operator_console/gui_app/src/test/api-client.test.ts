import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiClientError, apiGet, apiPost } from "@/lib/api/client";

describe("api client", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("unwraps result payloads from the canonical API envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          ok: true,
          workflow_version: "v2-service-layer",
          schema_version: "schema-1",
          generated_at: "2026-03-14T00:00:00+00:00",
          data: {
            result: {
              operation_run_id: "op-1",
            },
          },
          errors: [],
        }),
      }),
    );

    const response = await apiGet<{ operation_run_id: string }>("/runs");

    expect(response.data).toEqual({ operation_run_id: "op-1" });
  });

  it("preserves direct status payloads without requiring a result wrapper", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          ok: true,
          workflow_version: "v2-service-layer",
          schema_version: "schema-1",
          generated_at: "2026-03-14T00:00:00+00:00",
          data: {
            active_phase: "phase13",
          },
          errors: [],
        }),
      }),
    );

    const response = await apiGet<{ active_phase: string }>("/status");

    expect(response.data).toEqual({ active_phase: "phase13" });
  });

  it("surfaces envelope errors from non-2xx responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        json: async () => ({
          errors: [{ message: "folder_path must not be empty." }],
        }),
      }),
    );

    await expect(apiPost("/ingest", { folder_path: "" })).rejects.toMatchObject<ApiClientError>({
      name: "ApiClientError",
      message: "folder_path must not be empty.",
      status: 400,
    });
  });

  it("surfaces ok=false responses as ApiClientError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 409,
        json: async () => ({
          ok: false,
          workflow_version: "v2-service-layer",
          schema_version: "schema-1",
          generated_at: "2026-03-14T00:00:00+00:00",
          data: {},
          errors: [{ message: "version conflict" }],
        }),
      }),
    );

    await expect(
      apiPost("/policy", {
        selected_policy: "FIRST_SEEN",
        preferred_roots: [],
        recanonicalization_enabled: false,
        version: 1,
      }),
    ).rejects.toMatchObject<ApiClientError>({
      name: "ApiClientError",
      message: "version conflict",
      status: 409,
    });
  });
});
