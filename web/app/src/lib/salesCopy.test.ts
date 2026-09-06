import assert from "node:assert/strict";
import test from "node:test";
import type { SalesKnowledgeCard, SalesTurn } from "../api/client.ts";
import {
  NONE_SPECIFIED,
  KNOWLEDGE_CARD_FILTER_GROUP_NAME,
  KNOWLEDGE_CARD_FILTER_OPTIONS,
  KNOWLEDGE_CARD_POLICY_LABELS,
  KNOWLEDGE_REVIEW_CONFIRMATION_ROLE,
  activeObjection,
  beginKnowledgeReview,
  canConfirmKnowledgeReview,
  canReviewKnowledgeCard,
  classifySalesError,
  filterKnowledgeCards,
  isKnowledgeCardFilter,
  isKnowledgeCardVisibleInFilter,
  isSafeDomId,
  knowledgeCardDetailFields,
  knowledgeCardDomId,
  knowledgeCardFilterAccessibleLabel,
  knowledgeCardFilterCounts,
  knowledgeCardFilterInputId,
  knowledgeCardKey,
  knowledgeReviewConfirmation,
  knowledgeReviewConfirmationCancelsOnKey,
  knowledgeReviewFallbackFocusTarget,
  knowledgeReviewFocusTargetAfter,
  knowledgeReviewLiveMessage,
  knowledgeReviewPendingLabel,
  knowledgeSourceLabel,
  latestSalesTurnForConversation,
  partitionKnowledgeCardDetails,
  reasonCodeLabel,
  resolveKnowledgeReviewRestoreFocus,
  retainOpenCardDetails,
  salesMoveLabel,
  salesStageLabel,
} from "./salesCopy.ts";

test("sales stage labels stay distinct from process-state wording", () => {
  assert.equal(salesStageLabel("DISCOVERY"), "Discovery");
  assert.equal(salesStageLabel("WON"), "Won (sales conversation)");
  assert.equal(salesStageLabel("HUMAN_REVIEW"), "Needs you");
  assert.notEqual(salesStageLabel("WON"), "Won");
});

test("sales moves describe policy actions, not AI commercial control", () => {
  assert.equal(salesMoveLabel("OFFER_BOOKING_SLOTS"), "Offer booking slots");
  assert.equal(salesMoveLabel("ANSWER_OBJECTION"), "Answer with approved knowledge");
  assert.equal(salesMoveLabel("HANDOFF_TO_HUMAN"), "Hand off to you");
});

test("classifySalesError maps API codes to UI states", () => {
  assert.equal(classifySalesError({ status: 403, code: "forbidden" }), "denied");
  assert.equal(
    classifySalesError({ status: 404, code: "sales_playbook_not_found" }),
    "playbook_empty",
  );
  assert.equal(
    classifySalesError({ status: 404, code: "sales_profile_not_found" }),
    "profile_empty",
  );
  assert.equal(
    classifySalesError({ status: 404, code: "case_not_found" }),
    "case_missing",
  );
  assert.equal(classifySalesError({ status: 500, code: "unknown_error" }), "error");
  assert.equal(classifySalesError(new Error("offline")), "error");
});

test("knowledgeSourceLabel reads only title and location", () => {
  assert.deepEqual(
    knowledgeSourceLabel({ title: "Owner source", location: "section 1", prompt: "secret" }),
    { title: "Owner source", location: "section 1" },
  );
  assert.deepEqual(knowledgeSourceLabel({ extra: "ignored" }), { title: null, location: null });
});

function sampleCard(overrides: Partial<SalesKnowledgeCard> = {}): SalesKnowledgeCard {
  return {
    knowledge_id: "discovery-1",
    business_id: "biz-1",
    version: 1,
    status: "CANDIDATE",
    source: { title: "Owner source", location: "section 1", prompt: "secret" },
    principle: "Ask one relevant question.",
    applicable_when: ["stage == DISCOVERY"],
    prohibited_when: [],
    required_sequence: ["acknowledge", "ask"],
    forbidden_actions: ["invent_discount"],
    approved_examples: ["What is getting in the way today?"],
    created_at: "2026-09-06T08:00:00Z",
    reviewed_at: null,
    reviewed_by: "should-not-appear",
    ...overrides,
  };
}

test("knowledge card details include every policy section", () => {
  const fields = knowledgeCardDetailFields(sampleCard());
  const byLabel = Object.fromEntries(fields.map((field) => [field.label, field.values]));
  for (const label of KNOWLEDGE_CARD_POLICY_LABELS) {
    assert.ok(label in byLabel, `missing ${label}`);
  }
  assert.deepEqual(byLabel["Principle"], ["Ask one relevant question."]);
  assert.deepEqual(byLabel["Source title"], ["Owner source"]);
  assert.deepEqual(byLabel["Source location"], ["section 1"]);
  assert.deepEqual(byLabel["Knowledge ID"], ["discovery-1"]);
  assert.deepEqual(byLabel["Version"], ["1"]);
  assert.deepEqual(byLabel["Status"], ["Candidate"]);
  assert.deepEqual(byLabel["Applicable when"], ["stage == DISCOVERY"]);
  assert.deepEqual(byLabel["Prohibited when"], [NONE_SPECIFIED]);
  assert.deepEqual(byLabel["Required sequence"], ["acknowledge", "ask"]);
  assert.deepEqual(byLabel["Forbidden actions"], ["invent_discount"]);
  assert.deepEqual(byLabel["Approved examples"], ["What is getting in the way today?"]);
  assert.equal(JSON.stringify(fields).includes("secret"), false);
  assert.equal(JSON.stringify(fields).includes("should-not-appear"), false);
});

test("empty knowledge-card lists become None specified", () => {
  const fields = knowledgeCardDetailFields(sampleCard({
    source: {},
    principle: "   ",
    applicable_when: [],
    prohibited_when: ["  "],
    required_sequence: [],
    forbidden_actions: [],
    approved_examples: [],
  }));
  const byLabel = Object.fromEntries(fields.map((field) => [field.label, field.values]));
  assert.deepEqual(byLabel["Principle"], [NONE_SPECIFIED]);
  assert.deepEqual(byLabel["Source title"], [NONE_SPECIFIED]);
  assert.deepEqual(byLabel["Source location"], [NONE_SPECIFIED]);
  assert.deepEqual(byLabel["Applicable when"], [NONE_SPECIFIED]);
  assert.deepEqual(byLabel["Prohibited when"], [NONE_SPECIFIED]);
  assert.deepEqual(byLabel["Required sequence"], [NONE_SPECIFIED]);
  assert.deepEqual(byLabel["Forbidden actions"], [NONE_SPECIFIED]);
  assert.deepEqual(byLabel["Approved examples"], [NONE_SPECIFIED]);
});

test("only a candidate with open details can start review", () => {
  const candidate = sampleCard();
  assert.equal(canReviewKnowledgeCard("CANDIDATE"), true);
  assert.equal(canReviewKnowledgeCard("APPROVED"), false);
  assert.equal(canReviewKnowledgeCard("REJECTED"), false);
  assert.equal(canConfirmKnowledgeReview("CANDIDATE", false), false);
  assert.equal(canConfirmKnowledgeReview("CANDIDATE", true), true);
  assert.equal(canConfirmKnowledgeReview("APPROVED", true), false);
  assert.equal(beginKnowledgeReview(candidate, false, "approve"), null);
  assert.equal(beginKnowledgeReview({ ...candidate, status: "APPROVED" }, true, "reject"), null);
  assert.deepEqual(beginKnowledgeReview(candidate, true, "approve"), {
    knowledgeId: "discovery-1",
    version: 1,
    action: "approve",
  });
});

test("review confirmation names the card, version, action, and one-time warning", () => {
  const pending = beginKnowledgeReview(sampleCard(), true, "reject");
  assert.ok(pending);
  const copy = knowledgeReviewConfirmation(pending);
  assert.equal(copy.knowledgeId, "discovery-1");
  assert.equal(copy.version, 1);
  assert.equal(copy.action, "reject");
  assert.equal(copy.actionLabel, "rejection");
  assert.match(copy.warning, /only once/i);
});

test("filterKnowledgeCards is local and does not mutate the source list", () => {
  const candidate = sampleCard({ knowledge_id: "c1", status: "CANDIDATE" });
  const approved = sampleCard({ knowledge_id: "a1", status: "APPROVED" });
  const rejected = sampleCard({ knowledge_id: "r1", status: "REJECTED" });
  const cards = [candidate, approved, rejected];
  assert.deepEqual(filterKnowledgeCards(cards, "ALL").map((card) => card.knowledge_id), ["c1", "a1", "r1"]);
  assert.deepEqual(filterKnowledgeCards(cards, "CANDIDATE").map((card) => card.knowledge_id), ["c1"]);
  assert.deepEqual(filterKnowledgeCards(cards, "APPROVED").map((card) => card.knowledge_id), ["a1"]);
  assert.deepEqual(filterKnowledgeCards(cards, "REJECTED").map((card) => card.knowledge_id), ["r1"]);
  assert.equal(cards.length, 3);
  assert.deepEqual(knowledgeCardFilterCounts(cards), {
    ALL: 3,
    CANDIDATE: 1,
    APPROVED: 1,
    REJECTED: 1,
  });
});

test("retainOpenCardDetails keeps open cards that still exist after a refresh", () => {
  const kept = sampleCard({ knowledge_id: "keep-me", version: 2 });
  const gone = sampleCard({ knowledge_id: "gone", version: 1 });
  const open = {
    [knowledgeCardKey(kept)]: true,
    [knowledgeCardKey(gone)]: true,
    "stale:9": true,
    [knowledgeCardKey(sampleCard({ knowledge_id: "closed", version: 1 }))]: false,
  };
  assert.deepEqual(retainOpenCardDetails(open, [kept, sampleCard({ knowledge_id: "other", version: 1 })]), {
    [knowledgeCardKey(kept)]: true,
  });
});

test("knowledgeCardDomId stays unique, deterministic, and CSS-safe", () => {
  const dotted = sampleCard({ knowledge_id: "price.v1", version: 1 });
  const dashed = sampleCard({ knowledge_id: "price-v1", version: 1 });
  const dottedId = knowledgeCardDomId("knowledge-details", dotted);
  const dashedId = knowledgeCardDomId("knowledge-details", dashed);
  assert.notEqual(dottedId, dashedId);
  assert.equal(dottedId, knowledgeCardDomId("knowledge-details", dotted));
  assert.equal(dashedId, knowledgeCardDomId("knowledge-details", { ...dashed }));
  assert.ok(isSafeDomId(dottedId));
  assert.ok(isSafeDomId(dashedId));
  for (const id of [dottedId, dashedId]) {
    assert.doesNotMatch(id, /[ \/?#.]/);
    assert.equal(id.includes("price.v1"), false);
    assert.equal(id.includes("price-v1"), false);
  }
  assert.notEqual(
    knowledgeCardDomId("knowledge-details", sampleCard({ knowledge_id: "price.v1", version: 1 })),
    knowledgeCardDomId("knowledge-details", sampleCard({ knowledge_id: "price.v1", version: 2 })),
  );
});

test("knowledgeCardDomId encodes empty and unusual knowledge IDs safely", () => {
  const unusual = [
    sampleCard({ knowledge_id: "", version: 1 }),
    sampleCard({ knowledge_id: "  /?#.", version: 1 }),
    sampleCard({ knowledge_id: "sales.discovery/ask one?", version: 3 }),
    sampleCard({ knowledge_id: "цена v1", version: 1 }),
    sampleCard({ knowledge_id: "../id", version: 0 }),
  ];
  const ids = unusual.map((card) => knowledgeCardDomId("knowledge-details", card));
  assert.equal(new Set(ids).size, ids.length);
  for (const [index, card] of unusual.entries()) {
    const id = ids[index];
    assert.ok(isSafeDomId(id), id);
    assert.doesNotMatch(id, /[ \/?#]/);
    if (card.knowledge_id.length > 0) {
      assert.equal(id.includes(card.knowledge_id), false);
    }
    assert.equal(id, knowledgeCardDomId("knowledge-details", card));
  }
});

test("aria target ids for one card stay unique across prefixes", () => {
  const card = sampleCard({ knowledge_id: "price.v1", version: 1 });
  const ids = [
    knowledgeCardDomId("knowledge-details", card),
    knowledgeCardDomId("knowledge-details-toggle", card),
    knowledgeCardDomId("knowledge-review-title", card),
    knowledgeCardDomId("knowledge-review-warning", card),
  ];
  assert.equal(new Set(ids).size, ids.length);
  for (const id of ids) assert.ok(isSafeDomId(id));
});

test("full-card details split identity from wrapping policy rules", () => {
  const { identity, policy } = partitionKnowledgeCardDetails(knowledgeCardDetailFields(sampleCard()));
  assert.deepEqual(identity.map((field) => field.label), [
    "Principle",
    "Source title",
    "Source location",
    "Knowledge ID",
    "Version",
    "Status",
  ]);
  assert.deepEqual(policy.map((field) => field.label), [...KNOWLEDGE_CARD_POLICY_LABELS]);
});

test("review pending and live messages stay specific to the action", () => {
  assert.equal(knowledgeReviewPendingLabel("approve", false), "Confirm approval");
  assert.equal(knowledgeReviewPendingLabel("reject", true), "Rejecting…");
  assert.match(knowledgeReviewLiveMessage("success", "approve"), /approved/i);
  assert.match(knowledgeReviewLiveMessage("success", "reject"), /rejected/i);
  assert.equal(
    knowledgeReviewLiveMessage("error", "approve", "Only a candidate can be reviewed"),
    "Only a candidate can be reviewed",
  );
});

test("inline confirmation is a group and Escape cancels only when not reviewing", () => {
  assert.equal(KNOWLEDGE_REVIEW_CONFIRMATION_ROLE, "group");
  assert.equal(knowledgeReviewConfirmationCancelsOnKey("Escape", false), true);
  assert.equal(knowledgeReviewConfirmationCancelsOnKey("Escape", true), false);
  assert.equal(knowledgeReviewConfirmationCancelsOnKey("Enter", false), false);
  assert.equal(knowledgeReviewConfirmationCancelsOnKey("Tab", false), false);
  assert.equal(knowledgeReviewFocusTargetAfter("opened"), "confirm");
  assert.equal(knowledgeReviewFocusTargetAfter("cancelled"), "trigger");
  assert.equal(knowledgeReviewFocusTargetAfter("succeeded"), "details-toggle");
});

test("review restore focus uses the details toggle when the card stays visible", () => {
  const approved = sampleCard({ knowledge_id: "stay", status: "APPROVED" });
  const restore = knowledgeReviewFallbackFocusTarget({
    event: "succeeded",
    cardVisibleInCurrentFilter: isKnowledgeCardVisibleInFilter([approved], "ALL", approved),
    activeFilter: "ALL",
  });
  assert.equal(restore.target, "details-toggle");
  assert.equal(restore.filter, "ALL");
});

test("review restore focus uses the active filter input when a card leaves CANDIDATE", () => {
  const approved = sampleCard({ knowledge_id: "left", status: "APPROVED" });
  const restore = knowledgeReviewFallbackFocusTarget({
    event: "succeeded",
    cardVisibleInCurrentFilter: isKnowledgeCardVisibleInFilter([approved], "CANDIDATE", approved),
    activeFilter: "CANDIDATE",
  });
  assert.equal(restore.target, "filter-input");
  assert.equal(restore.filter, "CANDIDATE");
});

test("conflict refresh restore focus uses the active filter input when the card is gone", () => {
  const gone = sampleCard({ knowledge_id: "gone", version: 1 });
  const remaining = [sampleCard({ knowledge_id: "other", version: 1 })];
  const restore = knowledgeReviewFallbackFocusTarget({
    event: "conflict-refresh",
    cardVisibleInCurrentFilter: isKnowledgeCardVisibleInFilter(remaining, "CANDIDATE", gone),
    activeFilter: "CANDIDATE",
  });
  assert.equal(restore.target, "filter-input");
  assert.equal(restore.filter, "CANDIDATE");
});

test("cancel restore focus stays on the original Approve/Reject trigger", () => {
  const restore = knowledgeReviewFallbackFocusTarget({
    event: "cancelled",
    cardVisibleInCurrentFilter: true,
    activeFilter: "CANDIDATE",
  });
  assert.equal(restore.target, "trigger");
  assert.equal(knowledgeReviewFocusTargetAfter("cancelled"), "trigger");
  assert.equal(restore.filter, "CANDIDATE");
  assert.equal(
    knowledgeReviewFallbackFocusTarget({
      event: "cancelled",
      cardVisibleInCurrentFilter: false,
      activeFilter: "CANDIDATE",
    }).target,
    "trigger",
  );
});

test("successful review restore focus does not switch the selected filter", () => {
  for (const filter of ["ALL", "CANDIDATE", "APPROVED", "REJECTED"] as const) {
    const visible = knowledgeReviewFallbackFocusTarget({
      event: "succeeded",
      cardVisibleInCurrentFilter: true,
      activeFilter: filter,
    });
    const hidden = knowledgeReviewFallbackFocusTarget({
      event: "succeeded",
      cardVisibleInCurrentFilter: false,
      activeFilter: filter,
    });
    assert.equal(visible.filter, filter);
    assert.equal(hidden.filter, filter);
    assert.equal(visible.target, "details-toggle");
    assert.equal(hidden.target, "filter-input");
  }
});

test("restore focus falls back to the active filter radio when the details toggle is gone from the DOM", () => {
  const restore = knowledgeReviewFallbackFocusTarget({
    event: "succeeded",
    cardVisibleInCurrentFilter: false,
    activeFilter: "CANDIDATE",
  });
  assert.equal(
    resolveKnowledgeReviewRestoreFocus({
      restore,
      detailsToggle: { isConnected: false },
      trigger: { isConnected: false },
    }),
    "filter-input",
  );
  assert.equal(
    resolveKnowledgeReviewRestoreFocus({
      restore,
      detailsToggle: null,
      trigger: null,
    }),
    "filter-input",
  );
});

test("restore focus uses the details toggle only when that node is still in the document", () => {
  const restore = knowledgeReviewFallbackFocusTarget({
    event: "succeeded",
    cardVisibleInCurrentFilter: true,
    activeFilter: "ALL",
  });
  assert.equal(
    resolveKnowledgeReviewRestoreFocus({
      restore,
      detailsToggle: { isConnected: true },
      trigger: null,
    }),
    "details-toggle",
  );
  assert.equal(
    resolveKnowledgeReviewRestoreFocus({
      restore,
      detailsToggle: { isConnected: false },
      trigger: { isConnected: true },
    }),
    "filter-input",
  );
});

test("conflict refresh restore focus falls back when the reviewed card is no longer in the list", () => {
  const gone = sampleCard({ knowledge_id: "gone", version: 1 });
  const remaining = [sampleCard({ knowledge_id: "other", version: 1 })];
  const restore = knowledgeReviewFallbackFocusTarget({
    event: "conflict-refresh",
    cardVisibleInCurrentFilter: isKnowledgeCardVisibleInFilter(remaining, "CANDIDATE", gone),
    activeFilter: "CANDIDATE",
  });
  assert.equal(
    resolveKnowledgeReviewRestoreFocus({
      restore,
      detailsToggle: { isConnected: false },
      trigger: null,
    }),
    "filter-input",
  );
  assert.equal(restore.filter, "CANDIDATE");
});

test("cancel restore focus returns to Approve/Reject when that button remounts", () => {
  const restore = knowledgeReviewFallbackFocusTarget({
    event: "cancelled",
    cardVisibleInCurrentFilter: true,
    activeFilter: "CANDIDATE",
  });
  assert.equal(
    resolveKnowledgeReviewRestoreFocus({
      restore,
      detailsToggle: { isConnected: true },
      trigger: { isConnected: true },
    }),
    "trigger",
  );
  assert.equal(
    resolveKnowledgeReviewRestoreFocus({
      restore,
      detailsToggle: { isConnected: true },
      trigger: { isConnected: false },
    }),
    "filter-input",
  );
});

test("knowledge card filter options share one name and unique input ids", () => {
  const ids = KNOWLEDGE_CARD_FILTER_OPTIONS.map((option) => knowledgeCardFilterInputId(option.key));
  assert.equal(new Set(ids).size, ids.length);
  for (const option of KNOWLEDGE_CARD_FILTER_OPTIONS) {
    const id = knowledgeCardFilterInputId(option.key);
    assert.ok(id.startsWith(`${KNOWLEDGE_CARD_FILTER_GROUP_NAME}-`));
    assert.ok(isSafeDomId(id));
    assert.equal(isKnowledgeCardFilter(option.key), true);
  }
  assert.equal(isKnowledgeCardFilter("DRAFT"), false);
  assert.equal(knowledgeCardFilterAccessibleLabel("Candidates", null), "Candidates");
  assert.equal(knowledgeCardFilterAccessibleLabel("Candidates", 2), "Candidates (2)");
  assert.equal(knowledgeCardFilterAccessibleLabel("All", 0), "All (0)");
});

test("activeObjection ignores resolved and deferred rows", () => {
  const resolved = {
    objection_id: "o1",
    objection_type: "PRICE",
    status: "RESOLVED",
    cause: null,
    source_message_id: "m1",
    evidence_excerpt: "too expensive",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-02T00:00:00Z",
    version: 1,
  };
  const active = { ...resolved, objection_id: "o2", status: "ACTIVE", updated_at: "2026-09-03T00:00:00Z" };
  assert.equal(activeObjection([resolved, active])?.objection_id, "o2");
  assert.equal(activeObjection([resolved]), null);
});

function sampleTurn(overrides: Partial<SalesTurn> = {}): SalesTurn {
  return {
    turn_id: "t1",
    conversation_id: "conv-a",
    source_message_id: "m1",
    playbook_version: 1,
    stage_before: "GREETING",
    stage_after: "DISCOVERY",
    move: "GREET_AND_SET_CONTEXT",
    reason_code: "conversation_started",
    knowledge_ids: [],
    business_fact_ids: [],
    customer_evidence: [{ source_message_id: "m1", excerpt: "Hello from A" }],
    analysis: { hidden: true },
    validation: { hidden: true },
    created_at: "2026-09-06T08:00:00Z",
    ...overrides,
  };
}

test("latestSalesTurnForConversation picks the latest turn of this conversation", () => {
  const older = sampleTurn({ turn_id: "a-old", created_at: "2026-09-06T08:00:00Z" });
  const newer = sampleTurn({
    turn_id: "a-new",
    created_at: "2026-09-06T09:00:00Z",
    customer_evidence: [{ source_message_id: "m2", excerpt: "Later A" }],
  });
  assert.equal(latestSalesTurnForConversation([older, newer], "conv-a")?.turn_id, "a-new");
});

test("a newer turn from another conversation is ignored", () => {
  const current = sampleTurn({ turn_id: "a1", created_at: "2026-09-06T08:00:00Z" });
  const other = sampleTurn({
    turn_id: "b1",
    conversation_id: "conv-b",
    created_at: "2026-09-06T10:00:00Z",
    customer_evidence: [{ source_message_id: "m-b", excerpt: "From B" }],
  });
  assert.equal(latestSalesTurnForConversation([current, other], "conv-a")?.turn_id, "a1");
});

test("case-level turns with a null conversation_id are ignored", () => {
  const current = sampleTurn({ turn_id: "a1", created_at: "2026-09-06T08:00:00Z" });
  const orphan = sampleTurn({
    turn_id: "case-1",
    conversation_id: null,
    created_at: "2026-09-06T11:00:00Z",
  });
  assert.equal(latestSalesTurnForConversation([orphan, current], "conv-a")?.turn_id, "a1");
  assert.equal(latestSalesTurnForConversation([orphan], "conv-a"), null);
});

test("conversation provenance does not depend on input order", () => {
  const older = sampleTurn({ turn_id: "a-old", created_at: "2026-09-06T08:00:00Z" });
  const newer = sampleTurn({ turn_id: "a-new", created_at: "2026-09-06T09:00:00Z" });
  const other = sampleTurn({ turn_id: "b1", conversation_id: "conv-b", created_at: "2026-09-06T10:00:00Z" });
  assert.equal(latestSalesTurnForConversation([newer, other, older], "conv-a")?.turn_id, "a-new");
  assert.equal(latestSalesTurnForConversation([other, older, newer], "conv-a")?.turn_id, "a-new");
});

test("equal created_at is resolved stably by turn_id", () => {
  const left = sampleTurn({ turn_id: "turn-a", created_at: "2026-09-06T08:00:00Z" });
  const right = sampleTurn({ turn_id: "turn-b", created_at: "2026-09-06T08:00:00Z" });
  assert.equal(latestSalesTurnForConversation([left, right], "conv-a")?.turn_id, "turn-b");
  assert.equal(latestSalesTurnForConversation([right, left], "conv-a")?.turn_id, "turn-b");
});

test("unknown conversation returns null", () => {
  assert.equal(latestSalesTurnForConversation([sampleTurn()], "conv-missing"), null);
  assert.equal(latestSalesTurnForConversation([], "conv-a"), null);
});

test("reasonCodeLabel uses a known phrase, not a raw guarantee", () => {
  assert.equal(
    reasonCodeLabel("approved_objection_knowledge_missing"),
    "No approved knowledge card is available for this objection.",
  );
  assert.equal(reasonCodeLabel("custom_code"), "custom code");
});
