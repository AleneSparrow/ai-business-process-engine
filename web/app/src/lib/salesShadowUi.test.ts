import assert from "node:assert/strict";
import test from "node:test";
import type { SalesShadowResult } from "../api/client.ts";
import {
  SALES_SHADOW_EVALUATION_LABELS,
  SALES_SHADOW_EVALUATION_VALUES,
  SHADOW_NOT_SENT_NOTICE,
  SHADOW_SALES_UI_COPY,
  SHADOW_SALES_UI_KINDS,
  canSubmitShadowEvaluation,
  isSalesShadowEvaluation,
  isShadowAlreadyEvaluatedConflict,
  shadowEvaluationLiveMessage,
  shadowResultsForConversation,
  shadowSalesUiCopy,
  shadowSalesUiKindFromStatus,
} from "./salesShadowUi.ts";

function sampleShadow(overrides: Partial<SalesShadowResult> = {}): SalesShadowResult {
  return {
    shadow_id: "shadow-1",
    conversation_id: "conv-a",
    source_message_id: "msg-1",
    approved_move: "ASK_DISCOVERY_QUESTION",
    status: "VALID",
    proposed_response_text: "What outcome matters most?",
    delivered_response_text: "How can I help?",
    knowledge_ids: ["k1"],
    business_fact_ids: ["f1"],
    customer_evidence_ids: ["e1"],
    violations: [],
    prompt_version: "v1",
    model_name: "model",
    created_at: "2026-09-06T08:00:00Z",
    evaluation: null,
    evaluated_by: null,
    evaluated_at: null,
    ...overrides,
  };
}

test("backend shadow status maps onto the agreed presentation states", () => {
  assert.equal(shadowSalesUiKindFromStatus(null), "none");
  assert.equal(shadowSalesUiKindFromStatus(undefined), "none");
  assert.equal(shadowSalesUiKindFromStatus("PENDING"), "pending");
  assert.equal(shadowSalesUiKindFromStatus("VALID"), "valid");
  assert.equal(shadowSalesUiKindFromStatus("BLOCKED"), "blocked");
  assert.equal(shadowSalesUiKindFromStatus("PROVIDER_ERROR"), "provider_error");
  assert.equal(shadowSalesUiKindFromStatus("VALIDATOR_ERROR"), "validator_error");
  assert.equal(shadowSalesUiKindFromStatus("EVALUATED"), "evaluated");
  assert.deepEqual([...SHADOW_SALES_UI_KINDS], [
    "none",
    "pending",
    "valid",
    "blocked",
    "provider_error",
    "validator_error",
    "evaluated",
  ]);
});

test("shadow results are limited to the current conversation", () => {
  const current = sampleShadow({ shadow_id: "a", conversation_id: "conv-a" });
  const other = sampleShadow({ shadow_id: "b", conversation_id: "conv-b" });
  assert.deepEqual(
    shadowResultsForConversation([current, other], "conv-a").map((item) => item.shadow_id),
    ["a"],
  );
  assert.deepEqual(shadowResultsForConversation([other], "conv-a"), []);
});

test("human evaluation is one-time and only uses backend enum values", () => {
  const open = sampleShadow({ status: "VALID", evaluation: null });
  const done = sampleShadow({
    status: "EVALUATED",
    evaluation: "UNSAFE",
    evaluated_by: "user-1",
    evaluated_at: "2026-09-06T09:00:00Z",
  });
  assert.equal(canSubmitShadowEvaluation(open), true);
  assert.equal(canSubmitShadowEvaluation(open, true), false);
  assert.equal(canSubmitShadowEvaluation(done), false);
  assert.deepEqual([...SALES_SHADOW_EVALUATION_VALUES], ["APPROVED", "UNSAFE", "IRRELEVANT", "WRONG_TONE"]);
  assert.equal(isSalesShadowEvaluation("APPROVED"), true);
  assert.equal(isSalesShadowEvaluation("SEND_TO_CUSTOMER"), false);
  assert.equal(isShadowAlreadyEvaluatedConflict({ status: 409, code: "sales_shadow_already_evaluated" }), true);
  assert.equal(isShadowAlreadyEvaluatedConflict({ status: 409, code: "other" }), false);
});

test("shadow copy never implies the draft was delivered to the customer", () => {
  for (const kind of SHADOW_SALES_UI_KINDS) {
    const { description } = shadowSalesUiCopy({ kind });
    assert.doesNotMatch(description, /has been sent to the customer/i);
    assert.doesNotMatch(description, /send this (shadow )?reply to the customer/i);
    assert.ok(SHADOW_SALES_UI_COPY[kind].title.length > 0);
  }
  assert.match(SHADOW_NOT_SENT_NOTICE, /not sent to the customer/i);
  assert.doesNotMatch(SHADOW_NOT_SENT_NOTICE, /has been sent/i);
  assert.match(shadowSalesUiCopy("pending").description, /will not be sent/i);
  assert.match(shadowSalesUiCopy("valid").description, /has not been sent/i);
  assert.match(shadowEvaluationLiveMessage("success"), /never sent/i);
  for (const value of SALES_SHADOW_EVALUATION_VALUES) {
    assert.doesNotMatch(SALES_SHADOW_EVALUATION_LABELS[value], /sent to the customer/i);
  }
});
