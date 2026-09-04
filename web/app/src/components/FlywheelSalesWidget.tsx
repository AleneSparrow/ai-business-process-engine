import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { API_BASE } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { markSalesWidgetOpened } from "../lib/firstTouch";

const SCRIPT_ID = "flywheel-sales-widget";

/** True when this deployment is wired to sell Flywheel through its own engine. */
export function salesWidgetConfigured(): boolean {
  return Boolean(import.meta.env.VITE_SALES_BUSINESS_ID?.trim());
}

function removeWidget() {
  document.getElementById(SCRIPT_ID)?.remove();
  document.querySelectorAll("section.aibp-chat").forEach((node) => node.remove());
  document.querySelectorAll('link[href$="/widget/widget.css"]').forEach((node) => node.remove());
}

/**
 * Flywheel as customer zero: the marketing site is the first website the
 * engine actually sells on. Visitors who are not signed in get the live
 * widget. Owners inside /app or /onboarding do not — they would otherwise
 * chat with themselves while working a queue.
 */
export function FlywheelSalesWidget() {
  const { user, loading } = useAuth();
  const location = useLocation();
  const businessId = import.meta.env.VITE_SALES_BUSINESS_ID?.trim();
  const onOwnerSurface =
    location.pathname.startsWith("/app") || location.pathname.startsWith("/onboarding");

  useEffect(() => {
    if (!businessId || loading || user || onOwnerSurface) {
      removeWidget();
      return;
    }
    if (document.getElementById(SCRIPT_ID)) return;

    const script = document.createElement("script");
    script.id = SCRIPT_ID;
    script.src = `${API_BASE}/widget/widget.js`;
    script.dataset.businessId = businessId;
    script.dataset.apiBase = API_BASE;
    script.onload = () => markSalesWidgetOpened();
    document.body.append(script);

    return () => {
      // Keep the widget across / ↔ /lawyers ↔ /signup so the deal is not reset.
    };
  }, [businessId, loading, user, onOwnerSurface]);

  return null;
}
