import { Keyboard } from "lucide-react";

import { StatusBadge } from "@/components/StatusBadge";

export function DuplicateKeyboardShortcutsHint() {
  return (
    <div className="rounded-[24px] border border-border/70 bg-background/80 p-4 shadow-sm">
      <div className="flex items-center gap-2">
        <Keyboard className="h-4 w-4 text-muted-foreground" />
        <p className="text-sm font-semibold text-foreground">Shortcuts</p>
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        <StatusBadge label="← / → navigate" severity="neutral" />
        <StatusBadge label="1 Looks right" severity="success" />
        <StatusBadge label="2 Needs review" severity="destructive" />
        <StatusBadge label="3 Not sure" severity="caution" />
      </div>
    </div>
  );
}
