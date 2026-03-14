import { Dialog, DialogContent } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/StatusBadge";
import type { CanonicalFile } from "@/types/media";
import { FileIcon } from "lucide-react";

interface MediaPreviewModalProps {
  file: CanonicalFile | null;
  onClose: () => void;
}

export function MediaPreviewModal({ file, onClose }: MediaPreviewModalProps) {
  const isVideo = file?.mime_type?.startsWith("video/");

  return (
    <Dialog open={!!file} onOpenChange={() => onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-auto">
        {file && (
          <div className="space-y-4">
            <div className="aspect-video bg-muted rounded-lg flex items-center justify-center overflow-hidden">
              {file.thumbnail_url ? (
                isVideo ? (
                  <video src={file.thumbnail_url} controls className="w-full h-full object-contain" />
                ) : (
                  <img src={file.thumbnail_url} alt={file.path} className="w-full h-full object-contain" />
                )
              ) : (
                <FileIcon className="h-16 w-16 text-muted-foreground" />
              )}
            </div>
            <div className="space-y-3">
              <h3 className="font-semibold">{file.path.split("/").pop()}</h3>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-muted-foreground">Path:</span>
                  <p className="font-mono text-xs mt-0.5 break-all">{file.path}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Hash:</span>
                  <p className="font-mono text-xs mt-0.5 break-all">{file.hash}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Type:</span>
                  <p className="text-xs mt-0.5">{file.mime_type}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Size:</span>
                  <p className="text-xs mt-0.5">{(file.size_bytes / 1024).toFixed(1)} KB</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Created:</span>
                  <p className="text-xs mt-0.5">{new Date(file.created_at).toLocaleString()}</p>
                </div>
              </div>
              {file.tags && file.tags.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Tags</p>
                  <div className="flex flex-wrap gap-1.5">
                    {file.tags.map((tag) => (
                      <StatusBadge
                        key={tag.name}
                        label={`${tag.name} (${(tag.confidence * 100).toFixed(0)}%)`}
                        severity="info"
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
