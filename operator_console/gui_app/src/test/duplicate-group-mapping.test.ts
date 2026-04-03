import { describe, expect, it } from "vitest";

import { mapDuplicateGroups } from "@/lib/api/mappers/media";

describe("duplicate group mapping", () => {
  it("preserves duplicate recommendation from the API payload", () => {
    const [group] = mapDuplicateGroups({
      groups: [
        {
          group_id: "group-alpha",
          canonical_file: { absolute_path: "/library/alpha-main.jpg" },
          files: [
            {
              file_instance_id: "group-alpha-canonical",
              absolute_path: "/library/alpha-main.jpg",
              media_type: "IMG",
              is_image: true,
            },
            {
              file_instance_id: "group-alpha-duplicate-0",
              absolute_path: "/library/alpha-copy.jpg",
              media_type: "IMG",
              is_image: true,
            },
          ],
          duplicate_recommendation: {
            state: "SAFE_TO_MOVE_EXTRAS",
            classification: "INFO",
            primary_reason_code: "SAFE_TO_MOVE_REVIEWED_DUPLICATES",
            reason_codes: ["SAFE_TO_MOVE_REVIEWED_DUPLICATES"],
            operator_explanation: "Keep copy is healthy and the group is approved for movement.",
            review_is_stale: false,
            integrity_is_stale: false,
            lifecycle_context: {
              already_in_bin: false,
              restore_expired: false,
            },
            keep_summary: {
              identity_status: "KNOWN",
              integrity_status: "OK",
            },
            extra_summary: {
              health_class: "EXTRAS_ALL_HEALTHY",
              active_count: 1,
              healthy_count: 1,
              suspect_count: 0,
              broken_count: 0,
              unknown_count: 0,
            },
          },
        },
      ],
    });

    expect(group.duplicate_recommendation).toEqual({
      state: "SAFE_TO_MOVE_EXTRAS",
      classification: "INFO",
      primary_reason_code: "SAFE_TO_MOVE_REVIEWED_DUPLICATES",
      reason_codes: ["SAFE_TO_MOVE_REVIEWED_DUPLICATES"],
      operator_explanation: "Keep copy is healthy and the group is approved for movement.",
      review_is_stale: false,
      integrity_is_stale: false,
      lifecycle_context: {
        already_in_bin: false,
        restore_expired: false,
      },
      keep_summary: {
        identity_status: "KNOWN",
        integrity_status: "OK",
      },
      extra_summary: {
        health_class: "EXTRAS_ALL_HEALTHY",
        active_count: 1,
        healthy_count: 1,
        suspect_count: 0,
        broken_count: 0,
        unknown_count: 0,
      },
    });
  });
});
