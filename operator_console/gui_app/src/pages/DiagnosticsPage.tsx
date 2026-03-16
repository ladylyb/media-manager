import { Navigate, useSearchParams } from "react-router-dom";

export default function DiagnosticsPage() {
  const [searchParams] = useSearchParams();
  const tab = searchParams.get("tab") ?? "activity";

  return <Navigate replace to={`/admin?tab=${encodeURIComponent(tab)}`} />;
}
