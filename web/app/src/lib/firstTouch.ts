const STORAGE_KEY = "flywheel.first_touch";
const WINDOW_MS = 30 * 24 * 60 * 60 * 1000;

export interface FirstTouch {
  landing_path: string;
  landing_from: string | null;
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
  referrer_host: string | null;
  widget_opened: boolean;
  captured_at: string;
}

function param(search: URLSearchParams, key: string): string | null {
  const value = search.get(key)?.trim();
  return value || null;
}

function referrerHost(): string | null {
  try {
    if (!document.referrer) return null;
    const url = new URL(document.referrer);
    if (url.hostname === window.location.hostname) return null;
    return url.hostname;
  } catch {
    return null;
  }
}

function readStored(): FirstTouch | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as FirstTouch;
    if (!parsed?.captured_at || !parsed?.landing_path) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeStored(value: FirstTouch): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
}

function expired(value: FirstTouch): boolean {
  const captured = Date.parse(value.captured_at);
  if (Number.isNaN(captured)) return true;
  return Date.now() - captured > WINDOW_MS;
}

/** Keep the first landing inside a 30-day window. Later visits do not overwrite it. */
export function captureFirstTouch(): void {
  const existing = readStored();
  if (existing && !expired(existing)) return;

  const search = new URLSearchParams(window.location.search);
  writeStored({
    landing_path: window.location.pathname || "/",
    landing_from: param(search, "from"),
    utm_source: param(search, "utm_source"),
    utm_medium: param(search, "utm_medium"),
    utm_campaign: param(search, "utm_campaign"),
    referrer_host: referrerHost(),
    widget_opened: false,
    captured_at: new Date().toISOString(),
  });
}

export function markSalesWidgetOpened(): void {
  captureFirstTouch();
  const existing = readStored();
  if (!existing || existing.widget_opened) return;
  writeStored({ ...existing, widget_opened: true });
}

export function peekFirstTouch(): FirstTouch | null {
  const existing = readStored();
  if (!existing || expired(existing)) return null;
  return existing;
}

export function clearFirstTouch(): void {
  localStorage.removeItem(STORAGE_KEY);
}
