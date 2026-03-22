import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { MediaCard } from "@/components/media/MediaCard";
import { MediaGrid } from "@/components/media/MediaGrid";
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
      <MemoryRouter>
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
        />
      </MemoryRouter>,
    );

    const image = screen.getByAltText("clip.mov");
    expect(image.getAttribute("src")).toBe("/api/video-thumbnail/video-1");
  });

  it("falls back to a placeholder when the video poster fails to load", () => {
    render(
      <MemoryRouter>
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
        />
      </MemoryRouter>,
    );

    fireEvent.error(screen.getByAltText("fallback.mov"));

    expect(screen.getByText("Video preview unavailable")).toBeTruthy();
  });

  it("uses icon-only actions at small density", () => {
    render(
      <MemoryRouter>
        <MediaCard
          density="small"
          detailHref="/gallery/image-1"
          onPreview={() => undefined}
          file={{
            id: "image-1",
            filename: "first.jpg",
            file_type: "image",
            media_url: "/media/image-1",
            poster_url: null,
            matched_tags: [],
            top_confidence_score: null,
            sort_tag_name: null,
          }}
        />
      </MemoryRouter>,
    );

    expect(screen.queryByText("Quick preview")).toBeNull();
    expect(screen.queryByText("View details")).toBeNull();
    expect(screen.getByLabelText("Quick preview first.jpg")).toBeTruthy();
    expect(screen.getByLabelText("View details for first.jpg")).toBeTruthy();
  });

  it("hides preview text and extra tag count at compact density", () => {
    render(
      <MemoryRouter>
        <MediaCard
          density="compact"
          detailHref="/gallery/image-1"
          onPreview={() => undefined}
          file={{
            id: "image-1",
            filename: "first.jpg",
            file_type: "image",
            media_url: "/media/image-1",
            poster_url: null,
            matched_tags: ["tag-a", "tag-b"],
            top_confidence_score: 0.94,
            sort_tag_name: "tag-a",
          }}
        />
      </MemoryRouter>,
    );

    expect(screen.queryByText("Quick preview")).toBeNull();
    expect(screen.queryByText("+1 tags")).toBeNull();
    expect(screen.getByLabelText("View details for first.jpg")).toBeTruthy();
  });
});

describe("MediaGrid", () => {
  it("accepts a caller-provided grid layout class for density variations", () => {
    const { container } = render(
      <MemoryRouter>
        <MediaGrid
          files={[
            {
              id: "image-1",
              filename: "first.jpg",
              file_type: "image",
              media_url: "/media/image-1",
              poster_url: null,
              matched_tags: [],
              top_confidence_score: null,
              sort_tag_name: null,
            },
          ]}
          gridClassName="grid grid-cols-3 xl:grid-cols-7 gap-4"
        />
      </MemoryRouter>,
    );

    expect(container.querySelector(".grid")?.className).toContain("xl:grid-cols-7");
  });
});
