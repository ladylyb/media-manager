import type { LucideIcon } from "lucide-react";
import { Sparkles } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface TopSurfaceHeaderProps {
  badge: string;
  title: string;
  description: string;
  icon?: LucideIcon;
  density?: "default" | "compact";
  children?: ReactNode;
  className?: string;
  contentClassName?: string;
}

export function TopSurfaceHeader({
  badge,
  title,
  description,
  icon: Icon = Sparkles,
  density = "default",
  children,
  className,
  contentClassName,
}: TopSurfaceHeaderProps) {
  const compact = density === "compact";

  return (
    <section
      className={cn(
        "overflow-hidden rounded-[32px] border border-border/70 shadow-sm",
        "bg-[radial-gradient(circle_at_top_left,hsl(var(--primary)/0.18),transparent_36%),linear-gradient(135deg,hsl(var(--card))_0%,hsl(var(--secondary)/0.22)_100%)]",
        className,
      )}
    >
      <div
        className={cn(
          "space-y-5 px-6 py-6 lg:px-8",
          compact && "space-y-3 px-5 py-4 lg:px-6 lg:py-5",
          contentClassName,
        )}
      >
        <div className="inline-flex items-center gap-2 rounded-full border border-border/80 bg-background/85 px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-muted-foreground">
          <Icon className="h-3.5 w-3.5" />
          {badge}
        </div>
        <div className={cn("space-y-2", compact && "space-y-1.5")}>
          <h1 className={cn("text-3xl font-semibold tracking-tight text-foreground sm:text-4xl", compact && "text-3xl sm:text-3xl")}>
            {title}
          </h1>
          <p
            className={cn(
              "max-w-3xl text-sm leading-6 text-muted-foreground sm:text-base",
              compact && "max-w-4xl text-sm sm:text-sm",
            )}
          >
            {description}
          </p>
        </div>
        {children}
      </div>
    </section>
  );
}
