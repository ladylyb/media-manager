import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MediaCard } from "@/components/media/MediaCard";
import { mapCanonicalItems } from "@/lib/api/mappers/media";

describe("canonical media mapping", () => {
  it("maps poster_url for gallery video items", () => {
    const [item] = mapCanonicalItems([
      {
        id: "video-1",
        filename: "clip.mov",
        file_type: "video",
        media_url: "/media/video-1",
        poster_url: "/api/video-thumbnail/video-1",
        matched_tags: [],
        top_confidence_score: null,
        sort_tag_name: null,
      },
    ]);

    expect(item.poster_url).toBe("/api/video-thumbnail/video-1");
  });
});

describe("MediaCard", () => {
  it("renders a video poster when available", () => {
    render(
      <MediaCard
        file={{
          id: "video-1",
          filename: "clip.mov",
          file_type: "video",
          media_url: "/media/video-1",
          poster_url: "/api/video-thumbnail/video-1",
          matched_tags: [],
          top_confidence_score: null,
          sort_tag_name: null,
        }}
      />,
    );

    const image = screen.getByAltText("clip.mov");
    expect(image.getAttribute("src")).toBe("/api/video-thumbnail/video-1");
  });

  it("falls back to a placeholder when the video poster fails to load", () => {
    render(
      <MediaCard
        file={{
          id: "video-2",
          filename: "fallback.mov",
          file_type: "video",
          media_url: "/media/video-2",
          poster_url: "/api/video-thumbnail/video-2",
          matched_tags: [],
          top_confidence_score: null,
          sort_tag_name: null,
        }}
      />,
    );

    fireEvent.error(screen.getByAltText("fallback.mov"));

    expect(screen.getByText("Video preview unavailable")).toBeTruthy();
  });
});
