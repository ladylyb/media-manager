import { useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  destructive?: boolean;
  challengeWord?: string;
  onConfirm: () => void | Promise<void>;
  loading?: boolean;
  children?: React.ReactNode;
}

export function ConfirmDialog({
  open, onOpenChange, title, description, destructive, challengeWord, onConfirm, loading, children
}: ConfirmDialogProps) {
  const [challenge, setChallenge] = useState("");
  const challengeValid = !challengeWord || challenge === challengeWord;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {destructive && <AlertTriangle className="h-5 w-5 text-destructive" />}
            {title}
          </DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        {children}

        {challengeWord && (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              Type <span className="font-mono font-bold text-destructive">{challengeWord}</span> to confirm:
            </p>
            <input
              value={challenge}
              onChange={(e) => setChallenge(e.target.value)}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm font-mono"
              placeholder={challengeWord}
              autoFocus
            />
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={loading}>
            Cancel
          </Button>
          <Button
            variant={destructive ? "destructive" : "default"}
            onClick={async () => { await onConfirm(); setChallenge(""); }}
            disabled={!challengeValid || loading}
          >
            {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Confirm
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
