import { useState } from "react";
import { ErrorAlert } from "@/components/ErrorAlert";
import { StatusBadge } from "@/components/StatusBadge";
import { OperationRiskLabel } from "@/components/OperationRiskLabel";
import { Button } from "@/components/ui/button";
import { getPolicy, updatePolicy } from "@/lib/api/endpoints";
import { useApi } from "@/hooks/useApi";
import { useApiMutation } from "@/hooks/useApi";
import type { Policy as PolicyType } from "@/types/api";
import { Loader2, Save, Plus, X } from "lucide-react";
import { CardSkeleton } from "@/components/ui/LoadingSkeleton";
import { useQueryClient } from "@tanstack/react-query";

export default function Policy() {
  const queryClient = useQueryClient();
  const { data: policy, isLoading, error: loadError } = useApi<PolicyType>(["policy"], getPolicy);

  const [draft, setDraft] = useState<Partial<PolicyType>>({});
  const [newRoot, setNewRoot] = useState("");
  const [success, setSuccess] = useState(false);

  // Sync draft when policy loads
  const currentDraft = Object.keys(draft).length > 0 ? draft : policy;

  const mutation = useApiMutation(
    (d: Partial<PolicyType>) => updatePolicy(d),
    {
      onSuccess: (data) => {
        setDraft(data);
        queryClient.setQueryData(["policy"], data);
        setSuccess(true);
        setTimeout(() => setSuccess(false), 3000);
      },
    }
  );

  const addRoot = () => {
    if (newRoot && !currentDraft?.preferred_roots?.includes(newRoot)) {
      setDraft((prev) => ({ ...currentDraft, ...prev, preferred_roots: [...(currentDraft?.preferred_roots || []), newRoot] }));
      setNewRoot("");
    }
  };

  const removeRoot = (root: string) => {
    setDraft((prev) => ({ ...currentDraft, ...prev, preferred_roots: currentDraft?.preferred_roots?.filter((r) => r !== root) }));
  };

  if (isLoading) return <div className="p-6 space-y-4"><CardSkeleton /><CardSkeleton /><CardSkeleton /></div>;

  return (
    <div className="p-6 space-y-6 max-w-3xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Policy Configuration</h1>
          <p className="text-sm text-muted-foreground mt-1">Manage canonicalization and deduplication policies</p>
        </div>
        <OperationRiskLabel mutating label="Mutating Config" />
      </div>

      {loadError && <ErrorAlert message={loadError.message} />}
      {mutation.error && <ErrorAlert message={mutation.error.message} onDismiss={() => mutation.reset()} />}
      {success && <ErrorAlert message="Policy saved successfully" severity="info" />}

      <div className="space-y-6">
        <div className="rounded-lg border bg-card p-5 space-y-3">
          <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Selected Policy</label>
          <input
            value={currentDraft?.selected_policy || ""}
            onChange={(e) => setDraft({ ...currentDraft, selected_policy: e.target.value })}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm font-mono"
          />
        </div>

        <div className="rounded-lg border bg-card p-5 space-y-3">
          <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Preferred Roots</label>
          <div className="flex flex-wrap gap-2">
            {currentDraft?.preferred_roots?.map((root) => (
              <span key={root} className="inline-flex items-center gap-1 rounded-md bg-muted px-3 py-1.5 text-xs font-mono">
                {root}
                <button onClick={() => removeRoot(root)}><X className="h-3 w-3 text-muted-foreground hover:text-foreground" /></button>
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <input value={newRoot} onChange={(e) => setNewRoot(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addRoot()} placeholder="/media/primary" className="flex-1 rounded-md border bg-background px-3 py-2 text-sm font-mono" />
            <Button size="sm" variant="outline" onClick={addRoot}><Plus className="h-3.5 w-3.5 mr-1" />Add</Button>
          </div>
        </div>

        <div className="rounded-lg border bg-card p-5 flex items-center justify-between">
          <div>
            <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Recanonicalization</label>
            <p className="text-xs text-muted-foreground mt-1">Allow automatic recanonicalization on policy change</p>
          </div>
          <button
            onClick={() => setDraft({ ...currentDraft, recanonicalize: !currentDraft?.recanonicalize })}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${currentDraft?.recanonicalize ? "bg-primary" : "bg-muted"}`}
          >
            <span className={`inline-block h-4 w-4 transform rounded-full bg-card transition-transform ${currentDraft?.recanonicalize ? "translate-x-6" : "translate-x-1"}`} />
          </button>
        </div>

        {policy?.tie_breaker_preview && (
          <div className="rounded-lg border bg-card p-5 space-y-2">
            <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Tie-Breaker Preview</label>
            <p className="text-sm font-mono">{policy.tie_breaker_preview}</p>
            <StatusBadge label={`Version: ${policy.version}`} severity="info" />
          </div>
        )}

        <Button onClick={() => mutation.mutate(currentDraft || {})} disabled={mutation.isPending} className="w-full">
          {mutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
          Save Policy
        </Button>
      </div>
    </div>
  );
}
