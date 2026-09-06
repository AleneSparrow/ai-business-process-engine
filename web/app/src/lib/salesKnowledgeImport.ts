import type {
  SalesKnowledgeCardImport,
  SalesKnowledgeImportCheck,
  SalesKnowledgeImportRequest,
  SalesKnowledgeImportResponse,
  SalesKnowledgeSourceImport,
} from "../api/client";

export const KNOWLEDGE_IMPORT_CANDIDATE_NOTICE =
  "Every imported card is saved as Candidate. You cannot import a card as Approved or Rejected.";

export const KNOWLEDGE_IMPORT_CHECK_LABELS: Record<SalesKnowledgeImportCheck["status"], string> = {
  READY: "Ready to import as Candidate",
  DUPLICATE_VERSION: "This knowledge ID and version already exist",
};

export type ParsedKnowledgeImport =
  | {
      ok: true;
      request: SalesKnowledgeImportRequest;
      statusFieldIgnored: boolean;
    }
  | { ok: false; error: string };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function optionalTrimmedString(value: unknown): string | undefined {
  if (value === undefined || value === null) return undefined;
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

function requiredString(value: unknown): string | null {
  const trimmed = optionalTrimmedString(value);
  return trimmed ?? null;
}

function stringList(value: unknown, required: boolean): string[] | null | undefined {
  if (value === undefined) return required ? null : undefined;
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) return null;
  return value;
}

function normalizeSource(value: unknown): SalesKnowledgeSourceImport | null {
  if (!isRecord(value)) return null;
  const title = requiredString(value.title);
  const location = requiredString(value.location);
  if (!title || !location) return null;
  const source: SalesKnowledgeSourceImport = { title, location };
  const author = optionalTrimmedString(value.author);
  const edition = optionalTrimmedString(value.edition);
  const url = optionalTrimmedString(value.url);
  if (author) source.author = author;
  if (edition) source.edition = edition;
  if (url) source.url = url;
  return source;
}

function normalizeCard(value: unknown): { card: SalesKnowledgeCardImport; statusFieldIgnored: boolean } | null {
  if (!isRecord(value)) return null;
  const knowledgeId = requiredString(value.knowledge_id);
  const principle = requiredString(value.principle);
  const source = normalizeSource(value.source);
  const applicableWhen = stringList(value.applicable_when, true);
  const prohibitedWhen = stringList(value.prohibited_when, false);
  const requiredSequence = stringList(value.required_sequence, false);
  const forbiddenActions = stringList(value.forbidden_actions, false);
  const approvedExamples = stringList(value.approved_examples, false);
  if (
    !knowledgeId ||
    !principle ||
    !source ||
    !Array.isArray(applicableWhen) ||
    applicableWhen.length === 0 ||
    prohibitedWhen === null ||
    requiredSequence === null ||
    forbiddenActions === null ||
    approvedExamples === null
  ) {
    return null;
  }
  if (typeof value.version !== "number" || !Number.isInteger(value.version) || value.version < 1) {
    return null;
  }
  const card: SalesKnowledgeCardImport = {
    knowledge_id: knowledgeId,
    version: value.version,
    source,
    principle,
    applicable_when: applicableWhen,
  };
  if (prohibitedWhen) card.prohibited_when = prohibitedWhen;
  if (requiredSequence) card.required_sequence = requiredSequence;
  if (forbiddenActions) card.forbidden_actions = forbiddenActions;
  if (approvedExamples) card.approved_examples = approvedExamples;
  return { card, statusFieldIgnored: Object.prototype.hasOwnProperty.call(value, "status") };
}

export function parseKnowledgeImportJson(text: string): ParsedKnowledgeImport {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return { ok: false, error: "That file is not valid JSON." };
  }
  if (!isRecord(parsed) || !Array.isArray(parsed.cards)) {
    return { ok: false, error: "JSON must be an object with a cards array." };
  }
  if (parsed.cards.length === 0) {
    return { ok: false, error: "Import at least one knowledge card." };
  }
  const cards: SalesKnowledgeCardImport[] = [];
  let statusFieldIgnored = false;
  const identities = new Set<string>();
  for (const item of parsed.cards) {
    const normalized = normalizeCard(item);
    if (!normalized) {
      return { ok: false, error: "Each card must include knowledge_id, version, source, principle, and applicable_when." };
    }
    statusFieldIgnored = statusFieldIgnored || normalized.statusFieldIgnored;
    const identity = `${normalized.card.knowledge_id}:${normalized.card.version}`;
    if (identities.has(identity)) {
      return { ok: false, error: "knowledge_id and version must be unique within an import." };
    }
    identities.add(identity);
    cards.push(normalized.card);
  }
  return { ok: true, request: { cards }, statusFieldIgnored };
}

export function canCommitKnowledgeImport(result: SalesKnowledgeImportResponse | null): boolean {
  return result !== null && result.valid && !result.imported && result.cards_are_candidates === true;
}

export function isKnowledgeImportVersionConflict(err: unknown): boolean {
  return (
    typeof err === "object" &&
    err !== null &&
    "status" in err &&
    "code" in err &&
    (err as { status: unknown }).status === 409 &&
    (err as { code: unknown }).code === "sales_knowledge_version_conflict"
  );
}

export function knowledgeImportCheckLabel(check: SalesKnowledgeImportCheck): string {
  return KNOWLEDGE_IMPORT_CHECK_LABELS[check.status];
}

export function knowledgeImportLiveMessage(kind: "validated" | "imported" | "conflict", count?: number): string {
  if (kind === "validated") return "Validation finished. Review each card before writing.";
  if (kind === "conflict") return "One or more knowledge card versions already exist.";
  const n = count ?? 0;
  return n === 1
    ? "Imported 1 knowledge card as Candidate."
    : `Imported ${n} knowledge cards as Candidate.`;
}
