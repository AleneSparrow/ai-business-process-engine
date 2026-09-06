import type { SalesShadowEvaluation, SalesShadowResult, SalesShadowStatus } from "../api/client";

/**
 * Presentation mapping for GET/POST sales shadow-results.
 * UI kinds are not API enum values; status comes from SalesShadowStatus on the client.
 */

export const SHADOW_SALES_UI_KINDS = [
  "none",
  "pending",
  "valid",
  "blocked",
  "provider_error",
  "validator_error",
  "evaluated",
] as const;

export type ShadowSalesUiKind = (typeof SHADOW_SALES_UI_KINDS)[number];

export type ShadowSalesUiState = { kind: ShadowSalesUiKind };

export type ShadowSalesUiCopy = {
  title: string;
  description: string;
  tone: "neutral" | "info" | "success" | "warning" | "danger";
};

export const SHADOW_NOT_SENT_NOTICE = "This shadow reply was not sent to the customer.";

export const SHADOW_SALES_UI_COPY: Record<ShadowSalesUiKind, ShadowSalesUiCopy> = {
  none: {
    title: "No shadow result",
    description: "There is no shadow sales reply for this conversation. Nothing extra is shown until the engine produces one.",
    tone: "neutral",
  },
  pending: {
    title: "Generating shadow reply",
    description: "A shadow sales reply is being prepared. It will not be sent to the customer.",
    tone: "info",
  },
  valid: {
    title: "Shadow reply ready",
    description: "Policy accepted this draft. It is for staff comparison only and has not been sent.",
    tone: "success",
  },
  blocked: {
    title: "Shadow reply blocked",
    description: "Policy blocked this draft before it could be offered as a comparison. The customer still sees the live engine reply.",
    tone: "warning",
  },
  provider_error: {
    title: "Shadow provider error",
    description: "The language model did not return a usable shadow reply. The live conversation is unchanged.",
    tone: "danger",
  },
  validator_error: {
    title: "Shadow validator error",
    description: "The draft failed policy validation. It is not shown as an approved comparison and was not sent.",
    tone: "danger",
  },
  evaluated: {
    title: "Human evaluation recorded",
    description: "A reviewer already recorded a judgment on this shadow reply. The live conversation is unchanged.",
    tone: "info",
  },
};

const STATUS_TO_KIND: Record<SalesShadowStatus, Exclude<ShadowSalesUiKind, "none">> = {
  PENDING: "pending",
  VALID: "valid",
  BLOCKED: "blocked",
  PROVIDER_ERROR: "provider_error",
  VALIDATOR_ERROR: "validator_error",
  EVALUATED: "evaluated",
};

export const SALES_SHADOW_EVALUATION_VALUES = [
  "APPROVED",
  "UNSAFE",
  "IRRELEVANT",
  "WRONG_TONE",
] as const satisfies readonly SalesShadowEvaluation[];

export const SALES_SHADOW_EVALUATION_LABELS: Record<SalesShadowEvaluation, string> = {
  APPROVED: "Approved as a comparison",
  UNSAFE: "Unsafe",
  IRRELEVANT: "Irrelevant",
  WRONG_TONE: "Wrong tone",
};

export function shadowSalesUiKindFromStatus(status: SalesShadowStatus | null | undefined): ShadowSalesUiKind {
  if (!status) return "none";
  return STATUS_TO_KIND[status];
}

export function shadowSalesUiCopy(state: ShadowSalesUiState | ShadowSalesUiKind): ShadowSalesUiCopy {
  const kind = typeof state === "string" ? state : state.kind;
  return SHADOW_SALES_UI_COPY[kind];
}

export function shadowResultsForConversation(
  results: readonly SalesShadowResult[],
  conversationId: string,
): SalesShadowResult[] {
  return results.filter((result) => result.conversation_id === conversationId);
}

export function canSubmitShadowEvaluation(
  result: Pick<SalesShadowResult, "status" | "evaluation">,
  alreadySubmitted = false,
): boolean {
  if (alreadySubmitted) return false;
  return result.status !== "EVALUATED" && result.evaluation == null;
}

export function isSalesShadowEvaluation(value: string): value is SalesShadowEvaluation {
  return (SALES_SHADOW_EVALUATION_VALUES as readonly string[]).includes(value);
}

export function isShadowAlreadyEvaluatedConflict(err: unknown): boolean {
  return (
    typeof err === "object" &&
    err !== null &&
    "status" in err &&
    "code" in err &&
    (err as { status: unknown }).status === 409 &&
    (err as { code: unknown }).code === "sales_shadow_already_evaluated"
  );
}

export function shadowEvaluationLiveMessage(kind: "success" | "conflict"): string {
  if (kind === "conflict") return "This shadow result was already evaluated. Showing the recorded judgment.";
  return "Evaluation recorded. Shadow replies are never sent to the customer.";
}
