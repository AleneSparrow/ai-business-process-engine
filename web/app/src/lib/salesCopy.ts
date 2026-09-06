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

export type KnowledgeCardFilter = "ALL" | SalesKnowledgeStatus;

export type KnowledgeCardFilterCounts = Record<KnowledgeCardFilter, number>;

export const KNOWLEDGE_CARD_FILTER_OPTIONS: { key: KnowledgeCardFilter; label: string }[] = [
  { key: "ALL", label: "All" },
  { key: "CANDIDATE", label: "Candidates" },
  { key: "APPROVED", label: "Approved" },
  { key: "REJECTED", label: "Rejected" },
];

export const KNOWLEDGE_CARD_FILTER_GROUP_NAME = "knowledge-card-filter";

/** Conservative HTML id: letter first, then [A-Za-z0-9_-] only. */
const SAFE_DOM_ID = /^[A-Za-z][A-Za-z0-9_-]*$/;

export function isSafeDomId(value: string): boolean {
  return SAFE_DOM_ID.test(value);
}

export function isKnowledgeCardFilter(value: string): value is KnowledgeCardFilter {
  return KNOWLEDGE_CARD_FILTER_OPTIONS.some((option) => option.key === value);
}

export function knowledgeCardFilterInputId(filter: KnowledgeCardFilter): string {
  return `${KNOWLEDGE_CARD_FILTER_GROUP_NAME}-${filter}`;
}

export function knowledgeCardFilterAccessibleLabel(label: string, count: number | null): string {
  return count === null ? label : `${label} (${count})`;
}

export function knowledgeCardKey(card: { knowledge_id: string; version: number }): string {
  return `${card.knowledge_id}:${card.version}`;
}

function sanitizeDomPrefix(prefix: string): string {
  const cleaned = prefix.replace(/[^A-Za-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
  if (cleaned.length === 0) return "id";
  return /^[A-Za-z]/.test(cleaned) ? cleaned : `id-${cleaned}`;
}

/** Reversible UTF-8 hex. Distinct strings stay distinct after encoding. */
function encodeUtf8Hex(value: string): string {
  const bytes = new TextEncoder().encode(value);
  let hex = "";
  for (const byte of bytes) hex += byte.toString(16).padStart(2, "0");
  return hex;
}

/**
 * CSS/ARIA-safe id for a knowledge card node.
 * Encodes knowledge_id instead of stripping characters, so `price.v1` and
 * `price-v1` cannot collide. Not an API field.
 */
export function knowledgeCardDomId(
  prefix: string,
  card: { knowledge_id: string; version: number },
): string {
  const safePrefix = sanitizeDomPrefix(prefix);
  const encodedId = encodeUtf8Hex(card.knowledge_id);
  const version = Number.isFinite(card.version) ? String(Math.trunc(card.version)) : "0";
  return `${safePrefix}-${encodedId}-v${version}`;
}

export function filterKnowledgeCards<T extends { status: SalesKnowledgeStatus }>(
  cards: readonly T[],
  filter: KnowledgeCardFilter,
): T[] {
  return filter === "ALL" ? [...cards] : cards.filter((card) => card.status === filter);
}

export function knowledgeCardFilterCounts(
  cards: readonly { status: SalesKnowledgeStatus }[],
): KnowledgeCardFilterCounts {
  const counts: KnowledgeCardFilterCounts = { ALL: cards.length, CANDIDATE: 0, APPROVED: 0, REJECTED: 0 };
  for (const card of cards) counts[card.status] += 1;
  return counts;
}

/** Keep disclosure state across a card refresh when that card is still present. */
export function retainOpenCardDetails(
  openDetails: Record<string, boolean>,
  cards: readonly { knowledge_id: string; version: number }[],
): Record<string, boolean> {
  const remaining = new Set(cards.map(knowledgeCardKey));
  const next: Record<string, boolean> = {};
  for (const [key, isOpen] of Object.entries(openDetails)) {
    if (isOpen && remaining.has(key)) next[key] = true;
  }
  return next;
}

export function partitionKnowledgeCardDetails(fields: readonly KnowledgeCardDetailField[]): {
  identity: KnowledgeCardDetailField[];
  policy: KnowledgeCardDetailField[];
} {
  const policyLabels = new Set<string>(KNOWLEDGE_CARD_POLICY_LABELS);
  return {
    identity: fields.filter((field) => !policyLabels.has(field.label)),
    policy: fields.filter((field) => policyLabels.has(field.label)),
  };
}

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

export function knowledgeReviewPendingLabel(
  action: KnowledgeReviewAction,
  reviewing: boolean,
): string {
  if (reviewing) return action === "approve" ? "Approving…" : "Rejecting…";
  return action === "approve" ? "Confirm approval" : "Confirm rejection";
}

export function knowledgeReviewLiveMessage(
  kind: "success" | "error",
  action?: KnowledgeReviewAction,
  error?: string,
): string {
  if (kind === "error") return error?.trim() || "Could not review this knowledge card.";
  return action === "approve"
    ? "Knowledge card approved. It can now be used in customer replies."
    : "Knowledge card rejected. It will not be used in customer replies.";
}

/** Inline confirmation is a labelled group, not a modal dialog. */
export const KNOWLEDGE_REVIEW_CONFIRMATION_ROLE = "group" as const;

export function knowledgeReviewConfirmationCancelsOnKey(key: string, reviewing: boolean): boolean {
  return key === "Escape" && !reviewing;
}

export type KnowledgeReviewFocusTarget = "confirm" | "trigger" | "details-toggle" | "filter-input";

export type KnowledgeReviewFallbackFocusEvent = "succeeded" | "conflict-refresh" | "cancelled";

export type KnowledgeReviewFallbackFocus = {
  target: Exclude<KnowledgeReviewFocusTarget, "confirm">;
  filter: KnowledgeCardFilter;
};

export function knowledgeReviewFocusTargetAfter(
  event: "opened" | "cancelled" | "succeeded",
): KnowledgeReviewFocusTarget {
  if (event === "opened") return "confirm";
  if (event === "cancelled") return "trigger";
  return "details-toggle";
}

/**
 * Where to restore focus after a review action, without changing the filter.
 * Preferred target is the card's details toggle when that card is still in the
 * filtered list; otherwise the active filter radio. Cancel stays on Approve/Reject.
 */
export function knowledgeReviewFallbackFocusTarget(args: {
  event: KnowledgeReviewFallbackFocusEvent;
  cardVisibleInCurrentFilter: boolean;
  activeFilter: KnowledgeCardFilter;
}): KnowledgeReviewFallbackFocus {
  if (args.event === "cancelled") {
    return { target: "trigger", filter: args.activeFilter };
  }
  return {
    target: args.cardVisibleInCurrentFilter ? "details-toggle" : "filter-input",
    filter: args.activeFilter,
  };
}

function isConnectedElement(element: { isConnected?: boolean } | null | undefined): boolean {
  return element?.isConnected === true;
}

/**
 * DOM-aware restore: if the planned details toggle is gone (approve/reject under
 * CANDIDATE, or a conflict refresh), use the active filter radio. Does not change
 * the selected filter. Cancel still returns to Approve/Reject when that button
 * is back in the document.
 */
export function resolveKnowledgeReviewRestoreFocus(args: {
  restore: KnowledgeReviewFallbackFocus;
  detailsToggle: { isConnected?: boolean } | null | undefined;
  trigger: { isConnected?: boolean } | null | undefined;
}): Exclude<KnowledgeReviewFocusTarget, "confirm"> {
  if (args.restore.target === "trigger") {
    return isConnectedElement(args.trigger) ? "trigger" : "filter-input";
  }
  if (args.restore.target === "details-toggle" && isConnectedElement(args.detailsToggle)) {
    return "details-toggle";
  }
  return "filter-input";
}

export function isKnowledgeCardVisibleInFilter(
  cards: readonly { knowledge_id: string; version: number; status: SalesKnowledgeStatus }[],
  filter: KnowledgeCardFilter,
  card: { knowledge_id: string; version: number },
): boolean {
  const key = knowledgeCardKey(card);
  return filterKnowledgeCards(cards, filter).some((item) => knowledgeCardKey(item) === key);
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
