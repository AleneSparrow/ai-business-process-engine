/**
 * Thin fetch wrapper around the real backend (see src/api in the repo root).
 * Endpoints wired here are the ones that actually exist and are tested:
 *   POST /api/v1/auth/signup
 *   POST /api/v1/auth/login
 *   POST /api/v1/auth/logout
 *   GET  /api/v1/auth/me
 *   POST /api/v1/businesses          (self-serve onboarding)
 *   GET  /api/v1/businesses/{id}     (safe public metadata)
 *
 * There is deliberately no client here for a staff dashboard/conversation API —
 * that backend (Milestone 8 slice 2) has not been built yet. Dashboard/Conversation/
 * Settings pages in this app use static preview data until it exists.
 */

export interface ApiErrorPayload {
  code: string;
  message: string;
  request_id?: string;
  details?: unknown;
}

export class ApiError extends Error {
  code: string;
  status: number;
  details?: unknown;

  constructor(status: number, payload: ApiErrorPayload) {
    super(payload.message);
    this.name = "ApiError";
    this.code = payload.code;
    this.status = status;
    this.details = payload.details;
  }
}

const API_BASE = (import.meta.env.VITE_API_BASE ?? "http://localhost:8000").replace(/\/$/, "");

async function request<T>(path: string, options: RequestInit = {}, token?: string | null): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch {
    throw new ApiError(0, { code: "network_error", message: "Couldn't reach the server. Check your connection and try again." });
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const body = await response.json().catch(() => null);

  if (!response.ok) {
    const errorPayload: ApiErrorPayload = body?.error ?? {
      code: "unknown_error",
      message: "Something went wrong. Please try again.",
    };
    throw new ApiError(response.status, errorPayload);
  }

  return body as T;
}

export interface StaffUser {
  user_id: string;
  email: string;
  business_id: string | null;
}

export interface SessionResponse {
  token: string;
  expires_in_hours: number;
  user: StaffUser;
}

export interface BusinessCreatedResponse {
  business_id: string;
  name: string;
  widget_snippet: string;
}

export interface BusinessResponse {
  business_id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface OnboardingServicePayload {
  name: string;
  questions: string[];
}

export interface OnboardingPayload {
  business_name: string;
  industry: string;
  tone: string;
  services: OnboardingServicePayload[];
  service_zip_codes: string[];
  enforce_service_area: boolean;
}

export const api = {
  signup: (email: string, password: string) =>
    request<SessionResponse>("/api/v1/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  login: (email: string, password: string) =>
    request<SessionResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  logout: (token: string) => request<void>("/api/v1/auth/logout", { method: "POST" }, token),

  me: (token: string) => request<StaffUser>("/api/v1/auth/me", { method: "GET" }, token),

  createBusiness: (token: string, payload: OnboardingPayload) =>
    request<BusinessCreatedResponse>(
      "/api/v1/businesses",
      { method: "POST", body: JSON.stringify(payload) },
      token,
    ),

  getBusiness: (businessId: string) => request<BusinessResponse>(`/api/v1/businesses/${businessId}`),
};

export { API_BASE };
