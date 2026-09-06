import type { SalesKnowledgeStatus, SalesMove, SalesObjectionRecord, SalesPlaybookStatus, SalesStage, SalesTurn } from "../api/client";

export const NONE_SPECIFIED = "None specified";

/** Owner-facing labels for SalesStage. These are conversation progress, not ProcessState. */
export const SALES_STAGE_LABELS: Record<SalesStage, string> = {
  GREETING: "Greeting",
  DISCOVERY: "Discovery",
  NEEDS_CONFIRMED: "Needs confirmed",
  PRESENTATION: "Presentation",
  OBJECTION_HANDLING: "Objection handling",
  COMMITMENT: "Commitment",
  BOOKING: "Booking",
  NURTURE: "Nurture",
  FOLLOW_UP: "Follow-up",
  WON: "Won (sales conversation)",
  LOST: "Lost (sales conversation)",
  HUMAN_REVIEW: "Needs you",
};

export const SALES_MOVE_LABELS: Record<SalesMove, string> = {
  GREET_AND_SET_CONTEXT: "Greet and set context",
  ASK_DISCOVERY_QUESTION: "Ask a discovery question",
  REFLECT_CUSTOMER_NEED: "Reflect the customer need",
  CONFIRM_CUSTOMER_NEED: "Confirm the customer need",
  PRESENT_RELEVANT_VALUE: "Present approved value",
  PROVIDE_APPROVED_PROOF: "Share approved proof",
  DIAGNOSE_OBJECTION: "Diagnose the objection",
  ANSWER_OBJECTION: "Answer with approved knowledge",
  CHECK_OBJECTION_RESOLUTION: "Check whether the objection is resolved",
  ASK_FOR_COMMITMENT: "Ask for a next-step commitment",
  OFFER_BOOKING_SLOTS: "Offer booking slots",
  SCHEDULE_CALLBACK: "Schedule a callback",
  SEND_CONTEXTUAL_FOLLOW_UP: "Send a contextual follow-up",
  NURTURE_WITHOUT_PRESSURE: "Nurture without pressure",
  HANDOFF_TO_HUMAN: "Hand off to you",
  END_CONTACT: "End contact",
};

export const PLAYBOOK_STATUS_LABELS: Record<SalesPlaybookStatus, string> = {
  DRAFT: "Draft",
  PUBLISHED: "Published",
  ARCHIVED: "Archived",
};

export const KNOWLEDGE_STATUS_LABELS: Record<SalesKnowledgeStatus, string> = {
  CANDIDATE: "Candidate",
  APPROVED: "Approved",
  REJECTED: "Rejected",
};

const REASON_LABELS: Record<string, string> = {
  analysis_requires_human: "Policy requires a person to take this turn.",
  objection_requires_human: "This objection is marked for human review.",
  objection_cause_missing: "The objection is known, but its cause is not.",
  approved_objection_knowledge_missing: "No approved knowledge card is available for this objection.",
  approved_objection_knowledge_available: "Approved knowledge is available to answer the objection.",
  objection_answered_but_not_resolved: "The objection was answered, but the customer has not confirmed it is resolved.",
  customer_requested_callback: "The customer asked for a callback.",
  conversation_started: "The conversation just started.",
  required_discovery_context_missing: "The customer’s problem or desired outcome is still missing.",
  discovery_context_complete: "Discovery context is complete enough to confirm the need.",
  approved_presentation_knowledge_missing: "No approved knowledge card is available to present value.",
  confirmed_need_has_approved_value: "The need is confirmed and approved value can be presented.",
  customer_ready_and_booking_available: "The customer is ready, and booking is available.",
  customer_ready_without_booking_capability: "The customer is ready; booking is not offered automatically.",
  customer_not_ready_for_next_step: "The customer is not ready for a next step.",
  need_presented_without_active_objection: "Value was presented and there is no active objection.",
};

const CLOSED_OBJECTION = new Set(["RESOLVED", "DEFERRED"]);

export function salesStageLabel(stage: SalesStage): string {
  return SALES_STAGE_LABELS[stage];
}

export function salesMoveLabel(move: SalesMove): string {
  return SALES_MOVE_LABELS[move];
}

export function reasonCodeLabel(code: string): string {
  return REASON_LABELS[code] ?? code.replace(/_/g, " ");
}

export function knowledgeSourceLabel(source: Record<string, unknown>): { title: string | null; location: string | null } {
  const title = typeof source.title === "string" && source.title.trim() ? source.title.trim() : null;
  const location = typeof source.location === "string" && source.location.trim() ? source.location.trim() : null;
  return { title, location };
}

function listOrNone(values: readonly string[]): string[] {
  const cleaned = values.map((value) => value.trim()).filter((value) => value.length > 0);
  return cleaned.length > 0 ? cleaned : [NONE_SPECIFIED];
}

export type KnowledgeCardDetailField = {
  label: string;
  values: string[];
};

export function knowledgeCardDetailFields(card: {
  knowledge_id: string;
  version: number;
  status: SalesKnowledgeStatus;
  source: Record<string, unknown>;
  principle: string;
  applicable_when: readonly string[];
  prohibited_when: readonly string[];
  required_sequence: readonly string[];
  forbidden_actions: readonly string[];
  approved_examples: readonly string[];
}): KnowledgeCardDetailField[] {
  const source = knowledgeSourceLabel(card.source);
  const principle = card.principle.trim();
  return [
    { label: "Principle", values: [principle || NONE_SPECIFIED] },
    { label: "Source title", values: [source.title ?? NONE_SPECIFIED] },
    { label: "Source location", values: [source.location ?? NONE_SPECIFIED] },
    { label: "Knowledge ID", values: [card.knowledge_id] },
    { label: "Version", values: [String(card.version)] },
    { label: "Status", values: [KNOWLEDGE_STATUS_LABELS[card.status]] },
    { label: "Applicable when", values: listOrNone(card.applicable_when) },
    { label: "Prohibited when", values: listOrNone(card.prohibited_when) },
    { label: "Required sequence", values: listOrNone(card.required_sequence) },
    { label: "Forbidden actions", values: listOrNone(card.forbidden_actions) },
    { label: "Approved examples", values: listOrNone(card.approved_examples) },
  ];
}

export const KNOWLEDGE_CARD_POLICY_LABELS = [
  "Applicable when",
  "Prohibited when",
  "Required sequence",
  "Forbidden actions",
  "Approved examples",
] as const;

export function canReviewKnowledgeCard(status: SalesKnowledgeStatus): boolean {
  return status === "CANDIDATE";
}

export function canConfirmKnowledgeReview(status: SalesKnowledgeStatus, detailsOpen: boolean): boolean {
  return canReviewKnowledgeCard(status) && detailsOpen;
}

export type KnowledgeReviewAction = "approve" | "reject";

export type PendingKnowledgeReview = {
  knowledgeId: string;
  version: number;
  action: KnowledgeReviewAction;
};

export function beginKnowledgeReview(
  card: { knowledge_id: string; version: number; status: SalesKnowledgeStatus },
  detailsOpen: boolean,
  action: KnowledgeReviewAction,
): PendingKnowledgeReview | null {
  if (!canConfirmKnowledgeReview(card.status, detailsOpen)) return null;
  return { knowledgeId: card.knowledge_id, version: card.version, action };
}

export function knowledgeReviewConfirmation(pending: PendingKnowledgeReview): {
  knowledgeId: string;
  version: number;
  action: KnowledgeReviewAction;
  actionLabel: "approval" | "rejection";
  warning: string;
} {
  const actionLabel = pending.action === "approve" ? "approval" : "rejection";
  return {
    knowledgeId: pending.knowledgeId,
    version: pending.version,
    action: pending.action,
    actionLabel,
    warning: "This knowledge card can be reviewed only once. The decision cannot be changed.",
  };
}

export function isPendingReviewForCard(
  pending: PendingKnowledgeReview | null,
  card: { knowledge_id: string; version: number },
): pending is PendingKnowledgeReview {
  return pending !== null && pending.knowledgeId === card.knowledge_id && pending.version === card.version;
}

export function activeObjection(objections: SalesObjectionRecord[]): SalesObjectionRecord | null {
  const open = objections.filter((item) => !CLOSED_OBJECTION.has(item.status));
  if (open.length === 0) return null;
  return [...open].sort((left, right) => right.updated_at.localeCompare(left.updated_at))[0];
}

export function latestSalesTurnForConversation(
  turns: readonly SalesTurn[],
  conversationId: string,
): SalesTurn | null {
  const matching = turns.filter((turn) => turn.conversation_id === conversationId);
  if (matching.length === 0) return null;
  return matching.reduce((latest, turn) => {
    const byTime = turn.created_at.localeCompare(latest.created_at);
    if (byTime > 0) return turn;
    if (byTime < 0) return latest;
    return turn.turn_id.localeCompare(latest.turn_id) > 0 ? turn : latest;
  });
}

export type SalesRequestKind =
  | "denied"
  | "playbook_empty"
  | "profile_empty"
  | "case_missing"
  | "error";

function isApiErrorLike(err: unknown): err is { status: number; code: string } {
  return (
    typeof err === "object" &&
    err !== null &&
    "status" in err &&
    "code" in err &&
    typeof (err as { status: unknown }).status === "number" &&
    typeof (err as { code: unknown }).code === "string"
  );
}

export function classifySalesError(err: unknown): SalesRequestKind {
  if (!isApiErrorLike(err)) return "error";
  if (err.status === 403 || err.code === "forbidden") return "denied";
  if (err.status === 401 || err.code === "unauthorized") return "denied";
  if (err.status === 404 && err.code === "sales_playbook_not_found") return "playbook_empty";
  if (err.status === 404 && err.code === "sales_profile_not_found") return "profile_empty";
  if (err.status === 404 && err.code === "case_not_found") return "case_missing";
  return "error";
}
