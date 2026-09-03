export const ESCALATION_LABELS: Record<string, string> = {
  safety_emergency: "Safety or emergency language",
  urgent_request: "Customer requested urgent help",
  low_confidence: "Low confidence in the request",
  service_unclear: "Requested service was unclear",
  ai_review: "AI requested human review",
  service_area_uncertain: "Service area could not be confirmed",
  policy_review: "Business policy requires review",
  identity_conflict: "Contact details match another lead",
  already_pending: "Already waiting for review",
};

export const ESCALATION_ACTIONS: Record<string, string> = {
  safety_emergency: "Call or reply immediately — do not leave a safety issue in the queue.",
  urgent_request: "Reply today and confirm the next available option.",
  low_confidence: "Read the last message and clarify the customer’s request.",
  service_unclear: "Confirm which service the customer needs before proceeding.",
  ai_review: "Review the conversation and choose the next safe step.",
  service_area_uncertain: "Confirm the customer’s location before offering service.",
  policy_review: "Check this request against your business policy.",
  identity_conflict: "Verify the contact details before merging or continuing.",
  already_pending: "A teammate has already been asked to review this case.",
};

export const ESCALATION_OUTCOMES: Record<string, string> = {
  already_pending: "No automatic next step will happen until a teammate resolves it.",
};

export const ESCALATION_FEEDBACK_LABELS: Record<string, string> = {
  unnecessary: "Staff marked the escalation unnecessary",
  missed: "Staff marked a missed escalation",
  wrong_service: "Wrong service was assumed",
  identity_same_customer: "Same customer, duplicate identity",
  identity_different_customer: "Different customer, identity conflict",
};

export const CONVERSATION_STATUS_LABELS: Record<string, string> = {
  ai_active: "Engine handling",
  human_takeover_requested: "Needs you",
  human_takeover_active: "You took over",
  closed: "Closed",
};
