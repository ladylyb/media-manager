import { useEffect, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ErrorAlert } from "@/components/ErrorAlert";
import { TopSurfaceHeader } from "@/components/layout/TopSurfaceHeader";
import { MediaPreviewModal } from "@/components/media/MediaPreviewModal";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { getHome } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import { queryOptions } from "@/lib/api/queryOptions";
import type { CanonicalFile, HomePageData } from "@/types";
import { ArrowRight, Copy, ImageIcon, Images, Sparkles, Video } from "lucide-react";

function getErrorMessage(err: unknown): string | null {
  if (!err) return null;
  if (err instanceof Error) return err.message;
  return String(err);
}

function MediaThumbCard({
  file,
  onPreview,
}: {
  file: CanonicalFile;
  onPreview: (file: CanonicalFile) => void;
}) {
  const previewSrc = file.file_type === "video" ? file.poster_url ?? null : file.media_url;
  const [imageSrc, setImageSrc] = useState(previewSrc);

  useEffect(() => {
    setImageSrc(previewSrc);
  }, [previewSrc]);

  return (
    <button
      type="button"
      onClick={() => onPreview(file)}
      className="group overflow-hidden rounded-[24px] border border-border/80 bg-card text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg hover:shadow-primary/10"
    >
      <div className="relative aspect-[5/4] overflow-hidden bg-gradient-to-br from-muted via-muted to-secondary/60">
        {imageSrc ? (
          <img
            src={imageSrc}
            alt={file.filename}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
            onError={() => setImageSrc(null)}
          />
        ) : (
          <div className="flex h-full items-center justify-center">
            {file.file_type === "video" ? (
              <Video className="h-10 w-10 text-muted-foreground" />
            ) : (
              <ImageIcon className="h-10 w-10 text-muted-foreground" />
            )}
          </div>
        )}
        <div className="absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-black/65 via-black/15 to-transparent" />
        <div className="absolute left-3 top-3">
          <StatusBadge
            label={file.file_type === "video" ? "Video" : "Image"}
            severity="neutral"
            className="border-white/20 bg-background/85 text-foreground"
          />
        </div>
      </div>
      <div className="space-y-1 p-3">
        <p className="truncate text-sm font-semibold text-foreground">{file.filename}</p>
        <p className="truncate text-xs text-muted-foreground">
          {file.sort_tag_name ?? file.matched_tags[0] ?? "Ready for review"}
        </p>
      </div>
    </button>
  );
}

function SectionHeader({
  title,
  description,
  actionLabel,
  actionHref,
}: {
  title: string;
  description: string;
  actionLabel?: string;
  actionHref?: string;
}) {
  return (
    <div className="flex items-end justify-between gap-3">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      </div>
      {actionLabel && actionHref ? (
        <Button asChild variant="ghost" size="sm">
          <Link to={actionHref}>
            {actionLabel}
            <ArrowRight className="ml-2 h-4 w-4" />
          </Link>
        </Button>
      ) : null}
    </div>
  );
}

function QuickLinkCard({
  title,
  description,
  href,
  icon,
}: {
  title: string;
  description: string;
  href: string;
  icon: ReactNode;
}) {
  return (
    <Link
      to={href}
      className="rounded-2xl border border-border/70 bg-background/80 p-4 shadow-sm transition-colors hover:border-primary/35 hover:bg-primary/5"
    >
      <div className="flex items-start gap-3">
        <div className="rounded-xl border border-border/70 bg-card p-2">{icon}</div>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-foreground">{title}</p>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">{description}</p>
        </div>
      </div>
    </Link>
  );
}

function HeroSkeleton() {
  return (
    <div className="overflow-hidden rounded-[30px] border border-border/70 bg-[radial-gradient(circle_at_top_left,hsl(var(--primary)/0.18),transparent_36%),linear-gradient(135deg,hsl(var(--card))_0%,hsl(var(--secondary)/0.22)_100%)] p-6 shadow-sm">
      <div className="space-y-4">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-5 w-full max-w-2xl" />
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-24 rounded-2xl" />
          ))}
        </div>
      </div>
    </div>
  );
}

function EmptyMediaRow({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <Card className="rounded-[28px] border-dashed">
      <CardContent className="p-6">
        <p className="text-sm font-medium">{title}</p>
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const [selectedFile, setSelectedFile] = useState<CanonicalFile | null>(null);

  const homeQuery = useQuery({
    queryKey: queryKeys.home,
    queryFn: async () => (await getHome()).data as HomePageData,
    staleTime: queryOptions.home.staleTime,
  });

  const home = homeQuery.data;
  const error = getErrorMessage(homeQuery.error);
  const recentImages =
    home?.recent_images ?? home?.recent_media.filter((file) => file.file_type === "image") ?? [];
  const recentVideos =
    home?.recent_videos ?? home?.recent_media.filter((file) => file.file_type === "video") ?? [];

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 p-6">
      {homeQuery.isLoading && !home ? <HeroSkeleton /> : null}
      {error ? <ErrorAlert message={error} /> : null}

      {home ? (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.45fr)_22rem]">
          <div className="space-y-6">
            <TopSurfaceHeader
              badge="Library Overview"
              title="Media Manager"
              description="Browse recent media, review what needs attention, and jump into the guided workflow when you're ready."
              icon={Sparkles}
              className="rounded-[30px]"
            >
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-2xl border border-border/70 bg-background/85 p-4 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                    Total assets
                  </p>
                  <p className="mt-2 text-2xl font-semibold">{home.library_summary.total_assets}</p>
                </div>
                <div className="rounded-2xl border border-border/70 bg-background/85 p-4 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                    Images
                  </p>
                  <p className="mt-2 text-2xl font-semibold">{home.library_summary.images}</p>
                </div>
                <div className="rounded-2xl border border-border/70 bg-background/85 p-4 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                    Videos
                  </p>
                  <p className="mt-2 text-2xl font-semibold">{home.library_summary.videos}</p>
                </div>
                <div className="rounded-2xl border border-border/70 bg-background/85 p-4 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                    Duplicate groups
                  </p>
                  <p className="mt-2 text-2xl font-semibold">{home.library_summary.duplicate_groups}</p>
                </div>
              </div>
            </TopSurfaceHeader>

            <section className="space-y-4">
              <SectionHeader
                title="Recent Images"
                description="Newest image items ready for review."
                actionLabel="View All Media"
                actionHref="/gallery"
              />
              {recentImages.length ? (
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  {recentImages.map((file) => (
                    <MediaThumbCard key={file.id} file={file} onPreview={setSelectedFile} />
                  ))}
                </div>
              ) : (
                <EmptyMediaRow
                  title="No recent images yet"
                  description="Image uploads will appear here once they are added to the library."
                />
              )}
            </section>

            <section className="space-y-4">
              <SectionHeader
                title="Recent Videos"
                description="Newest video items ready for review."
                actionLabel="View All Media"
                actionHref="/gallery"
              />
              {recentVideos.length ? (
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  {recentVideos.map((file) => (
                    <MediaThumbCard key={file.id} file={file} onPreview={setSelectedFile} />
                  ))}
                </div>
              ) : (
                <EmptyMediaRow
                  title="No recent videos yet"
                  description="Video uploads will appear here once they are added to the library."
                />
              )}
            </section>
          </div>

          <div className="space-y-6 xl:sticky xl:top-6 xl:self-start">
            <Card className="rounded-[28px] border-border/70 bg-background/90 shadow-sm">
              <CardHeader className="pb-3">
                <CardDescription>Go where you need to work</CardDescription>
                <CardTitle className="text-xl">Quick Links</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <Button asChild className="w-full justify-between">
                  <Link to={home.guided_entry?.route ?? "/pipeline-wizard"}>
                    {home.guided_entry?.label ?? "Open Organize Media"}
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
                <p className="text-sm leading-6 text-muted-foreground">
                  {home.guided_entry?.helper ?? "Guided ingest, planning, apply, and review"}
                </p>
                <div className="grid gap-3 pt-2">
                  <QuickLinkCard
                    title="Review Duplicates"
                    description="Inspect duplicate groups and confirm which items need review."
                    href="/duplicates"
                    icon={<Copy className="h-4 w-4" />}
                  />
                  <QuickLinkCard
                    title="Open Library"
                    description="Browse canonical media with previews, filters, and detail pages."
                    href="/gallery"
                    icon={<Images className="h-4 w-4" />}
                  />
                </div>
              </CardContent>
            </Card>

            <Card className="rounded-[28px] border-border/70 shadow-sm">
              <CardHeader className="pb-3">
                <CardDescription>Items that need review before you continue</CardDescription>
                <CardTitle className="text-xl">Needs Attention</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <Link
                  to="/duplicates"
                  className="flex items-center justify-between rounded-2xl border border-border/70 bg-background/80 p-4 transition-colors hover:border-primary/35 hover:bg-primary/5"
                >
                  <div>
                    <p className="text-sm font-semibold">Duplicate groups</p>
                    <p className="mt-1 text-sm text-muted-foreground">Review likely duplicate clusters.</p>
                  </div>
                  <span className="text-2xl font-semibold">{home.attention_summary.duplicate_groups}</span>
                </Link>
                <Link
                  to="/admin/diagnostics?tab=activity"
                  className="flex items-center justify-between rounded-2xl border border-border/70 bg-background/80 p-4 transition-colors hover:border-primary/35 hover:bg-primary/5"
                >
                  <div>
                    <p className="text-sm font-semibold">Failed runs</p>
                    <p className="mt-1 text-sm text-muted-foreground">Open Admin Diagnostics to review jobs that need follow-up.</p>
                  </div>
                  <span className="text-2xl font-semibold">{home.attention_summary.failed_runs}</span>
                </Link>
                <div className="flex items-center justify-between rounded-2xl border border-border/70 bg-background/80 p-4">
                  <div>
                    <p className="text-sm font-semibold">Untagged assets</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Canonical items that still need metadata enrichment.
                    </p>
                  </div>
                  <span className="text-2xl font-semibold">{home.attention_summary.untagged_assets}</span>
                </div>
                <div className="rounded-2xl border border-primary/15 bg-primary/5 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                    Recommended workflow
                  </p>
                  <p className="mt-2 text-sm leading-6 text-foreground/90">
                    Start in Organize Media for guided ingest and review, then use Duplicates and
                    Gallery as follow-up tools when you want more detail. Use Admin Diagnostics if
                    a job needs troubleshooting.
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      ) : null}

      <MediaPreviewModal file={selectedFile} onClose={() => setSelectedFile(null)} />
    </div>
  );
}
