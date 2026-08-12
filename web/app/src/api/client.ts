/**
 * Thin fetch wrapper around the real backend (see src/api in the repo root).
 * Endpoints wired here are the ones that actually exist and are tested:
 *   POST /api/v1/auth/signup
 *   POST /api/v1/auth/login
 *   POST /api/v1/auth/logout
 *   GET  /api/v1/auth/me
 *   POST /api/v1/businesses                                    (self-serve onboarding)
 *   GET  /api/v1/businesses/{id}                                (safe public metadata)
 *   GET  /api/v1/businesses/{id}/cases                          (Milestone 8 slice 2)
 *   GET  /api/v1/businesses/{id}/cases/{case_id}                (Milestone 8 slice 2)
 *   GET  /api/v1/businesses/{id}/conversations                  (Milestone 8 slice 2)
 *   GET  /api/v1/businesses/{id}/conversations/{conversation_id} (Milestone 8 slice 2)
 *
 * The dashboard endpoints above are read-only for now — there is no reply/mark-resolved
 * backend yet, so Settings and the reply box in Conversation still use preview data.
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

export type ProcessState =
  | "NEW_LEAD"
  | "CONTACTED"
  | "QUALIFYING"
  | "QUALIFIED"
  | "BOOKED"
  | "QUOTED"
  | "FOLLOW_UP"
  | "WON"
  | "PAID"
  | "COMPLETED"
  | "REVIEW_REQUESTED"
  | "REACTIVATION"
  | "NEEDS_HUMAN"
  | "LOST"
  | "CANCELLED";

export interface DashboardLead {
  lead_id: string;
  name: string | null;
  email: string | null;
  phone: string | null;
}

export interface DashboardCaseSummary {
  case_id: string;
  lead: DashboardLead;
  current_state: ProcessState;
  created_at: string;
  updated_at: string;
  event_count: number;
  latest_event_type: string | null;
}

export interface DashboardCaseListResponse {
  cases: DashboardCaseSummary[];
}

export interface DashboardEvent {
  event_id: string;
  event_type: string;
  source: string;
  occurred_at: string;
  payload: Record<string, unknown>;
}

export interface DashboardCaseDetail {
  case_id: string;
  lead: DashboardLead;
  current_state: ProcessState;
  created_at: string;
  updated_at: string;
  events: DashboardEvent[];
}

export interface DashboardConversationSummary {
  conversation_id: string;
  case_id: string | null;
  lead_id: string | null;
  lead_name: string | null;
  case_state: ProcessState | null;
  channel: string;
  status: "ai_active" | "human_takeover_requested" | "human_takeover_active" | "closed";
  created_at: string;
  last_activity_at: string;
}

export interface DashboardConversationListResponse {
  conversations: DashboardConversationSummary[];
}

export interface DashboardMessage {
  message_id: string;
  direction: "inbound" | "outbound";
  role: "customer" | "assistant" | "human" | "system";
  text: string;
  created_at: string;
}

export interface DashboardConversationDetail {
  conversation: DashboardConversationSummary;
  messages: DashboardMessage[];
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

  listCases: (token: string, businessId: string) =>
    request<DashboardCaseListResponse>(`/api/v1/businesses/${businessId}/cases`, { method: "GET" }, token),

  getCase: (token: string, businessId: string, caseId: string) =>
    request<DashboardCaseDetail>(`/api/v1/businesses/${businessId}/cases/${caseId}`, { method: "GET" }, token),

  listConversations: (token: string, businessId: string) =>
    request<DashboardConversationListResponse>(
      `/api/v1/businesses/${businessId}/conversations`,
      { method: "GET" },
      token,
    ),

  getConversation: (token: string, businessId: string, conversationId: string) =>
    request<DashboardConversationDetail>(
      `/api/v1/businesses/${businessId}/conversations/${conversationId}`,
      { method: "GET" },
      token,
    ),
};

export { API_BASE };
