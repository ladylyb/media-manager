import { Navigate } from "react-router-dom";

export default function PolicyPage() {
  return <Navigate replace to="/admin?tab=library-rules" />;
}
