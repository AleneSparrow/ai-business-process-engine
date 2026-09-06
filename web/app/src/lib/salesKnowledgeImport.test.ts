import assert from "node:assert/strict";
import test from "node:test";
import type { SalesKnowledgeImportResponse } from "../api/client.ts";
import {
  KNOWLEDGE_IMPORT_CANDIDATE_NOTICE,
  canCommitKnowledgeImport,
  isKnowledgeImportVersionConflict,
  knowledgeImportCheckLabel,
  knowledgeImportLiveMessage,
  parseKnowledgeImportJson,
} from "./salesKnowledgeImport.ts";

const validCard = {
  knowledge_id: "imported-1",
  version: 1,
  source: { title: "Verified source", location: "chapter 2" },
  principle: "Ask one grounded question.",
  applicable_when: ["stage == DISCOVERY"],
};

test("import validation requires a cards array and keeps only contract fields", () => {
  const parsed = parseKnowledgeImportJson(JSON.stringify({
    cards: [{ ...validCard, prohibited_when: ["already answered"], extra: "drop-me" }],
  }));
  assert.equal(parsed.ok, true);
  if (!parsed.ok) return;
  assert.deepEqual(parsed.request.cards[0].knowledge_id, "imported-1");
  assert.equal("status" in parsed.request.cards[0], false);
  assert.equal("extra" in parsed.request.cards[0], false);
  assert.equal(parsed.statusFieldIgnored, false);
});

test("a status field cannot override Candidate on import", () => {
  const parsed = parseKnowledgeImportJson(JSON.stringify({
    cards: [{ ...validCard, status: "APPROVED" }],
  }));
  assert.equal(parsed.ok, true);
  if (!parsed.ok) return;
  assert.equal(parsed.statusFieldIgnored, true);
  assert.equal("status" in parsed.request.cards[0], false);
  assert.match(KNOWLEDGE_IMPORT_CANDIDATE_NOTICE, /Candidate/);
  assert.match(KNOWLEDGE_IMPORT_CANDIDATE_NOTICE, /cannot import a card as Approved/i);
});

test("duplicate knowledge_id and version in the file is rejected before write", () => {
  const parsed = parseKnowledgeImportJson(JSON.stringify({
    cards: [validCard, { ...validCard }],
  }));
  assert.equal(parsed.ok, false);
  if (parsed.ok) return;
  assert.match(parsed.error, /unique/i);
});

test("commit is allowed only after a successful dry-run", () => {
  const ready: SalesKnowledgeImportResponse = {
    valid: true,
    imported: false,
    cards_are_candidates: true,
    checks: [{ knowledge_id: "imported-1", version: 1, status: "READY" }],
  };
  const duplicate: SalesKnowledgeImportResponse = {
    valid: false,
    imported: false,
    cards_are_candidates: true,
    checks: [{ knowledge_id: "imported-1", version: 1, status: "DUPLICATE_VERSION" }],
  };
  const written: SalesKnowledgeImportResponse = {
    valid: true,
    imported: true,
    cards_are_candidates: true,
    checks: [{ knowledge_id: "imported-1", version: 1, status: "READY" }],
  };
  assert.equal(canCommitKnowledgeImport(null), false);
  assert.equal(canCommitKnowledgeImport(ready), true);
  assert.equal(canCommitKnowledgeImport(duplicate), false);
  assert.equal(canCommitKnowledgeImport(written), false);
  assert.match(knowledgeImportCheckLabel(duplicate.checks[0]), /already exist/i);
  assert.match(knowledgeImportLiveMessage("imported", 1), /Candidate/i);
});

test("write conflict is detected from the backend version-conflict code", () => {
  assert.equal(
    isKnowledgeImportVersionConflict({ status: 409, code: "sales_knowledge_version_conflict" }),
    true,
  );
  assert.equal(
    isKnowledgeImportVersionConflict({ status: 409, code: "sales_knowledge_already_reviewed" }),
    false,
  );
  assert.match(knowledgeImportLiveMessage("conflict"), /already exist/i);
});
