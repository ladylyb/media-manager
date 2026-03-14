import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

interface Column<T> {
  key: string;
  header: string;
  render?: (item: T) => React.ReactNode;
  sortable?: boolean;
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  loading?: boolean;
  emptyMessage?: string;
  onRowClick?: (item: T) => void;
  className?: string;
  sortKey?: string;
  sortOrder?: "asc" | "desc";
  onSort?: (key: string) => void;
}

export function DataTable<T extends object>({
  columns, data, loading, emptyMessage = "No data available", onRowClick, className, sortKey, sortOrder, onSort
}: DataTableProps<T>) {
  if (loading) {
    return (
      <div className={cn("rounded-lg border bg-card overflow-hidden", className)}>
        <table className="w-full">
          <thead>
            <tr className="border-b bg-muted/50">
              {columns.map(col => (
                <th key={col.key} className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: 5 }).map((_, i) => (
              <tr key={i} className="border-b last:border-0">
                {columns.map(col => (
                  <td key={col.key} className="px-4 py-3"><Skeleton className="h-4 w-full max-w-[120px]" /></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (!data.length) {
    return (
      <div className={cn("rounded-lg border bg-card p-8 text-center", className)}>
        <p className="text-sm text-muted-foreground">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className={cn("rounded-lg border bg-card overflow-hidden overflow-x-auto", className)}>
      <table className="w-full">
        <thead>
          <tr className="border-b bg-muted/50">
            {columns.map(col => (
              <th
                key={col.key}
                onClick={() => col.sortable && onSort?.(col.key)}
                className={cn(
                  "px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider",
                  col.sortable && "cursor-pointer hover:text-foreground select-none",
                  col.className
                )}
              >
                <span className="inline-flex items-center gap-1">
                  {col.header}
                  {col.sortable && sortKey === col.key && (
                    <span className="text-foreground">{sortOrder === "asc" ? "↑" : "↓"}</span>
                  )}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((item, i) => (
            <tr
              key={i}
              onClick={() => onRowClick?.(item)}
              className={cn(
                "border-b last:border-0 transition-colors",
                onRowClick && "cursor-pointer hover:bg-muted/50"
              )}
            >
              {columns.map(col => (
                <td key={col.key} className={cn("px-4 py-3 text-sm", col.className)}>
                  {col.render ? col.render(item) : String((item as Record<string, unknown>)[col.key] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
