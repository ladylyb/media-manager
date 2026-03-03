import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ErrorAlert } from "@/components/ErrorAlert";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { JsonViewer } from "@/components/JsonViewer";
import { Button } from "@/components/ui/button";
import { adminDbReset, invalidateAllReadsAfterDbReset } from "@/lib/api/endpoints";
import type { DbResetPreview, DbResetResult } from "@/types/api";
import { AlertTriangle, Loader2, Trash2, Eye } from "lucide-react";

export default function AdminPage() {
  const queryClient = useQueryClient();
  const [preview, setPreview] = useState<DbResetPreview | null>(null);
  const [result, setResult] = useState<DbResetResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const handleDryRun = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await adminDbReset({ dry_run: true });
      setPreview(res.data as DbResetPreview);
    } catch (err: any) { setError(err.message); }
    finally { setLoading(false); }
  };

  const handleExecute = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await adminDbReset({ dry_run: false, challenge_word: "media-manager" });
      setResult(res.data as DbResetResult);
      setPreview(null);
      await invalidateAllReadsAfterDbReset(queryClient);
    } catch (err: any) { setError(err.message); }
    finally { setLoading(false); setConfirmOpen(false); }
  };

  return (
    <div className="p-6 space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Admin</h1>
        <p className="text-sm text-muted-foreground mt-1">Destructive system operations — proceed with caution</p>
      </div>

      {error && <ErrorAlert message={error} onDismiss={() => setError(null)} />}

      {/* DB Reset */}
      <div className="rounded-lg border-2 border-destructive/30 bg-destructive/5 p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-md bg-destructive/10">
            <AlertTriangle className="h-6 w-6 text-destructive" />
          </div>
          <div>
            <h2 className="font-bold text-lg">Database Reset</h2>
            <p className="text-sm text-muted-foreground">Permanently delete all data from the media pipeline database. This action cannot be undone.</p>
          </div>
        </div>

        <div className="flex gap-3">
          <Button variant="outline" onClick={handleDryRun} disabled={loading}>
            {loading && !confirmOpen ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Eye className="mr-2 h-4 w-4" />}
            Preview (Dry Run)
          </Button>
          <Button variant="destructive" onClick={() => setConfirmOpen(true)} disabled={loading || !preview}>
            <Trash2 className="mr-2 h-4 w-4" />
            Execute Reset
          </Button>
        </div>

        {preview && (
          <div className="space-y-3">
            <h3 className="text-sm font-semibold">Affected Tables</h3>
            <div className="grid grid-cols-2 gap-2">
              {preview.affected_tables.map(table => (
                <div key={table} className="rounded-md border bg-card p-3 flex items-center justify-between">
                  <span className="text-sm font-mono">{table}</span>
                  <span className="text-xs font-mono text-destructive font-bold">planned</span>
                </div>
              ))}
            </div>
            {preview.warnings && preview.warnings.length > 0 && (
              <div className="space-y-1">
                {preview.warnings.map((w, i) => (
                  <ErrorAlert key={i} message={w} severity="warning" />
                ))}
              </div>
            )}
          </div>
        )}

        {result && (
          <div className="space-y-3">
            <ErrorAlert message={result.message} severity={result.success ? "info" : "error"} />
            <JsonViewer data={result} title="Reset Result" />
          </div>
        )}
      </div>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Confirm Database Reset"
        description="This will permanently delete ALL data from the media pipeline database. This action is irreversible."
        destructive
        challengeWord="media-manager"
        onConfirm={handleExecute}
        loading={loading}
      >
        {preview && (
          <div className="text-sm text-muted-foreground">
            <p className="font-semibold">Tables to be cleared:</p>
            <ul className="list-disc list-inside mt-1">
              {preview.affected_tables.map(t => <li key={t} className="font-mono text-xs">{t}</li>)}
            </ul>
          </div>
        )}
      </ConfirmDialog>
    </div>
  );
}
