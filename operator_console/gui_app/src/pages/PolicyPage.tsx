import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorAlert } from "@/components/ErrorAlert";
import { StatusBadge } from "@/components/StatusBadge";
import { OperationRiskLabel } from "@/components/OperationRiskLabel";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  getPolicy,
  invalidateReadsAfterPolicyUpdate,
  updatePolicy,
} from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import { queryOptions } from "@/lib/api/queryOptions";
import type { Policy } from "@/types/api";
import { FolderTree, GitCompareArrows, Loader2, Plus, Save, ShieldCheck, X } from "lucide-react";
import { CardSkeleton } from "@/components/Skeletons";

function getErrorMessage(err: unknown): string | null {
  if (!err) return null;
  if (err instanceof Error) return err.message;
  return String(err);
}

export default function PolicyPage() {
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [draft, setDraft] = useState<Partial<Policy>>({});
  const [newRoot, setNewRoot] = useState("");

  const policyQuery = useQuery({
    queryKey: queryKeys.policy,
    queryFn: async () => (await getPolicy()).data,
    staleTime: queryOptions.policy.staleTime,
  });

  const policy = (policyQuery.data as Policy | undefined) ?? null;

  useEffect(() => {
    if (policyQuery.data) {
      setDraft(policyQuery.data as Policy);
    }
  }, [policyQuery.data]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      const res = await updatePolicy(draft);
      setDraft(res.data);
      await invalidateReadsAfterPolicyUpdate(queryClient);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err: unknown) {
      setError(getErrorMessage(err) || "Failed to update policy");
    } finally {
      setSaving(false);
    }
  };

  const addRoot = () => {
    if (newRoot && !draft.preferred_roots?.includes(newRoot)) {
      setDraft(prev => ({
        ...prev,
        preferred_roots: [...(prev.preferred_roots || []), newRoot],
      }));
      setNewRoot("");
    }
  };

  const removeRoot = (root: string) => {
    setDraft(prev => ({
      ...prev,
      preferred_roots: prev.preferred_roots?.filter(r => r !== root),
    }));
  };

  if (policyQuery.isLoading && !policy) {
    return (
      <div className="space-y-4 p-6">
        <CardSkeleton />
        <CardSkeleton />
        <CardSkeleton />
      </div>
    );
  }

  const combinedError = error || getErrorMessage(policyQuery.error);
  const hasChanges = JSON.stringify(draft) !== JSON.stringify(policy ?? {});

  return (
    <div className="max-w-3xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Policy Configuration</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage canonicalization and deduplication policies
          </p>
        </div>
        <OperationRiskLabel mutating label="Mutating Config" />
      </div>

      {combinedError && (
        <ErrorAlert message={combinedError} onDismiss={() => setError(null)} />
      )}
      {success && <ErrorAlert message="Policy saved successfully" severity="info" />}

      <div className="grid gap-3 md:grid-cols-3">
        <Card className="border-primary/15 bg-gradient-to-br from-card via-card to-primary/5">
          <CardContent className="flex items-center gap-3 p-5">
            <ShieldCheck className="h-5 w-5 text-primary" />
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Selected Policy</p>
              <p className="mt-1 font-mono text-sm">{draft.selected_policy || "--"}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 p-5">
            <FolderTree className="h-5 w-5 text-primary" />
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Preferred Roots</p>
              <p className="mt-1 font-mono text-sm">{draft.preferred_roots?.length ?? 0}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 p-5">
            <GitCompareArrows className="h-5 w-5 text-primary" />
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Change State</p>
              <p className="mt-1 text-sm">{hasChanges ? "Unsaved edits" : "In sync"}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="space-y-6">
        <Card>
          <CardHeader className="pb-3">
            <CardDescription>Policy Selection</CardDescription>
            <CardTitle className="text-xl">Canonicalization strategy</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Selected Policy
            </label>
            <Input
              value={draft.selected_policy || ""}
              onChange={e =>
                setDraft(prev => ({ ...prev, selected_policy: e.target.value }))
              }
              className="font-mono"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardDescription>Root Preferences</CardDescription>
            <CardTitle className="text-xl">Preferred media roots</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-2">
              {draft.preferred_roots?.map(root => (
                <span
                  key={root}
                  className="inline-flex items-center gap-1 rounded-md bg-muted px-3 py-1.5 text-xs font-mono"
                >
                  {root}
                  <button onClick={() => removeRoot(root)}>
                    <X className="h-3 w-3 text-muted-foreground hover:text-foreground" />
                  </button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <Input
                value={newRoot}
                onChange={e => setNewRoot(e.target.value)}
                onKeyDown={e => e.key === "Enter" && addRoot()}
                placeholder="/media/primary"
                className="font-mono"
              />
              <Button size="sm" variant="outline" onClick={addRoot}>
                <Plus className="mr-1 h-3.5 w-3.5" />Add
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardDescription>Recanonicalization</CardDescription>
            <CardTitle className="text-xl">Automatic policy follow-through</CardTitle>
          </CardHeader>
          <CardContent className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm">Allow automatic recanonicalization on policy change</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Keep this disabled if you want policy edits reviewed before downstream canonical changes are applied.
              </p>
            </div>
            <Switch
              checked={Boolean(draft.recanonicalization_enabled)}
              onCheckedChange={checked =>
                setDraft(prev => ({
                  ...prev,
                  recanonicalization_enabled: checked,
                }))
              }
            />
          </CardContent>
        </Card>

        {policy?.tie_breaker_preview && (
          <Card>
            <CardHeader className="pb-3">
              <CardDescription>Tie-Breaker Preview</CardDescription>
              <CardTitle className="text-xl">Current decision heuristic</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm font-mono">{policy.tie_breaker_preview}</p>
              <StatusBadge label={`Version: ${policy.version}`} severity="info" />
            </CardContent>
          </Card>
        )}

        <Button onClick={handleSave} disabled={saving || !hasChanges} className="w-full">
          {saving ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Save className="mr-2 h-4 w-4" />
          )}
          {saving ? "Saving Policy" : hasChanges ? "Save Policy" : "No Changes To Save"}
        </Button>
      </div>
    </div>
  );
}
