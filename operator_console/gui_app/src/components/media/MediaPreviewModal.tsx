import { StatusBadge } from "@/components/StatusBadge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { CanonicalFile } from "@/types";
import { cn } from "@/lib/utils";
import { FileIcon, ImageIcon, Video } from "lucide-react";

interface MediaPreviewModalProps {
  file: CanonicalFile | null;
  onClose: () => void;
}

function renderConfidence(score: number | null | undefined) {
  if (score == null) return "Unknown";
  return `${Math.round(score * 100)}%`;
}

export function MediaPreviewModal({ file, onClose }: MediaPreviewModalProps) {
  const isVideo = file?.file_type === "video";

  return (
    <Dialog open={!!file} onOpenChange={() => onClose()}>
      <DialogContent className="max-h-[92vh] max-w-4xl overflow-auto border-none bg-transparent p-0 shadow-none">
        {file ? (
          <div className="overflow-hidden rounded-[28px] border border-white/10 bg-slate-950 text-slate-50 shadow-2xl">
            <div className="grid min-h-[32rem] lg:grid-cols-[minmax(0,1.35fr)_24rem]">
              <div className="relative flex items-center justify-center bg-[radial-gradient(circle_at_top,hsl(210_100%_60%_/_0.18),transparent_35%),linear-gradient(180deg,hsl(222_45%_10%),hsl(222_45%_6%))] p-4 sm:p-6">
                {file.media_url ? (
                  isVideo ? (
                    <video
                      src={file.media_url}
                      controls
                      className="max-h-[72vh] w-full rounded-2xl border border-white/10 bg-black object-contain"
                    />
                  ) : (
                    <img
                      src={file.media_url}
                      alt={file.filename}
                      className="max-h-[72vh] w-full rounded-2xl border border-white/10 bg-black object-contain"
                    />
                  )
                ) : (
                  <div className="flex h-[24rem] w-full items-center justify-center rounded-2xl border border-dashed border-white/15 bg-white/[0.03]">
                    {isVideo ? (
                      <Video className="h-16 w-16 text-slate-400" />
                    ) : file.file_type === "image" ? (
                      <ImageIcon className="h-16 w-16 text-slate-400" />
                    ) : (
                      <FileIcon className="h-16 w-16 text-slate-400" />
                    )}
                  </div>
                )}
              </div>

              <div className="flex flex-col gap-6 border-t border-white/10 bg-white/[0.03] p-6 lg:border-l lg:border-t-0">
                <DialogHeader className="space-y-3 text-left">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge
                      label={isVideo ? "Video" : "Image"}
                      severity="info"
                      className="border-white/15 bg-white/10 text-slate-100"
                    />
                    <StatusBadge
                      label={`Confidence ${renderConfidence(file.top_confidence_score)}`}
                      severity="neutral"
                      className="border-white/15 bg-white/5 text-slate-200"
                    />
                  </div>
                  <DialogTitle className="break-words text-2xl font-semibold text-white">
                    {file.filename}
                  </DialogTitle>
                  <DialogDescription className="text-slate-300">
                    Canonical media preview backed by the current `/api/*` integration layer.
                  </DialogDescription>
                </DialogHeader>

                <div className="grid gap-3 text-sm sm:grid-cols-2">
                  <InfoCard label="Media ID" value={file.id} mono />
                  <InfoCard label="Type" value={file.file_type} />
                  <InfoCard label="Primary tag" value={file.sort_tag_name ?? file.matched_tags[0] ?? "None"} />
                  <InfoCard label="Tag count" value={String(file.matched_tags.length)} />
                </div>

                <div className="space-y-3">
                  <h3 className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">
                    Media URL
                  </h3>
                  <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                    <p className="break-all font-mono text-xs text-slate-200">{file.media_url || "Unavailable"}</p>
                  </div>
                </div>

                <div className="space-y-3">
                  <h3 className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">
                    Matched tags
                  </h3>
                  {file.matched_tags.length ? (
                    <div className="flex flex-wrap gap-2">
                      {file.matched_tags.map((tag) => (
                        <StatusBadge
                          key={tag}
                          label={tag}
                          severity={tag === file.sort_tag_name ? "success" : "neutral"}
                          className={cn(
                            "border-white/15 text-slate-100",
                            tag === file.sort_tag_name ? "bg-emerald-500/20" : "bg-white/5",
                          )}
                        />
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-slate-400">No tags available for this item.</p>
                  )}
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

interface InfoCardProps {
  label: string;
  value: string;
  mono?: boolean;
}

function InfoCard({ label, value, mono = false }: InfoCardProps) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/15 p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">{label}</p>
      <p className={cn("mt-2 text-sm text-slate-100", mono && "break-all font-mono text-xs")}>{value}</p>
    </div>
  );
}
