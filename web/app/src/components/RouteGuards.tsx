import type { ReactElement } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

function FullscreenLoader() {
  return (
    <div className="min-h-screen w-full flex items-center justify-center" style={{ backgroundColor: "#F7F6F2" }}>
      <span className="text-sm text-[#6B7280]">Loading…</span>
    </div>
  );
}

/** Sends anonymous visitors to log in before reaching an authenticated page. */
export function RequireAuth({ children }: { children: ReactElement }) {
  const { user, token, loading } = useAuth();
  const location = useLocation();
  if (loading) return <FullscreenLoader />;
  if (!token || !user) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  return children;
}

/** Sends authenticated owners with no business yet into the onboarding wizard. */
export function RequireBusiness({ children }: { children: ReactElement }) {
  const { user, loading } = useAuth();
  if (loading) return <FullscreenLoader />;
  if (user && !user.business_id) return <Navigate to="/onboarding" replace />;
  return children;
}

/** Onboarding itself: skip straight to the dashboard once a business already exists. */
export function RequireNoBusiness({ children }: { children: ReactElement }) {
  const { user, loading } = useAuth();
  if (loading) return <FullscreenLoader />;
  if (user?.business_id) return <Navigate to="/app" replace />;
  return children;
}
