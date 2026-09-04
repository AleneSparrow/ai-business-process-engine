import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { captureFirstTouch } from "../lib/firstTouch";

/** Records the first public landing so signup can send first-touch attribution. */
export function CaptureFirstTouch() {
  const location = useLocation();
  useEffect(() => {
    if (location.pathname.startsWith("/app") || location.pathname.startsWith("/onboarding")) {
      return;
    }
    captureFirstTouch();
  }, [location.pathname, location.search]);
  return null;
}
