import { useEffect, useMemo, useRef, useState } from "react";
import { BookOpen, Check, Loader2, Upload, X } from "lucide-react";
import { describeError } from "../auth/AuthContext";
import {
  ApiError,
  api,
  type SalesKnowledgeCard,
  type SalesKnowledgeImportRequest,
  type SalesKnowledgeImportResponse,
  type SalesPlaybook,
} from "../api/client";
import { formatRelativeTime } from "./Shared";
import {
  KNOWLEDGE_CARD_FILTER_GROUP_NAME,
  KNOWLEDGE_CARD_FILTER_OPTIONS,
  KNOWLEDGE_REVIEW_CONFIRMATION_ROLE,
  KNOWLEDGE_STATUS_LABELS,
  PLAYBOOK_STATUS_LABELS,
  beginKnowledgeReview,
  canConfirmKnowledgeReview,
  canReviewKnowledgeCard,
  classifySalesError,
  filterKnowledgeCards,
  isKnowledgeCardFilter,
  isKnowledgeCardVisibleInFilter,
  isPendingReviewForCard,
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
  partitionKnowledgeCardDetails,
  resolveKnowledgeReviewRestoreFocus,
  retainOpenCardDetails,
  type KnowledgeCardDetailField,
  type KnowledgeCardFilter,
  type KnowledgeReviewAction,
  type KnowledgeReviewFallbackFocus,
  type PendingKnowledgeReview,
} from "../lib/salesCopy";
import {
  KNOWLEDGE_IMPORT_CANDIDATE_NOTICE,
  canCommitKnowledgeImport,
  isKnowledgeImportVersionConflict,
  knowledgeImportCheckLabel,
  knowledgeImportLiveMessage,
  parseKnowledgeImportJson,
} from "../lib/salesKnowledgeImport";

/**
 * Settings → Sales Playbook. Live sales API: playbook versions, knowledge
 * cards, approve/reject, and candidate-only JSON import (validate then write).
 * A published playbook is read-only. Cadence/quiet-hours are not on this contract.
 */

const FOCUS_RING =
  "outline-none focus-visible:ring-2 focus-visible:ring-[#B87333] focus-visible:ring-offset-2";

const FILTER_PILL =
  `inline-flex items-center px-3 py-1.5 rounded-lg text-xs font-medium border cursor-pointer ${FOCUS_RING} has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-[#B87333] has-[:focus-visible]:ring-offset-2`;

function statusTone(status: SalesKnowledgeCard["status"]): { color: string; backgroundColor: string } {
  if (status === "APPROVED") return { color: "#1E7B52", backgroundColor: "#E9F5EF" };
  if (status === "REJECTED") return { color: "#8A3225", backgroundColor: "#FBEBE9" };
  return { color: "#8A561B", backgroundColor: "#FFF8EE" };
}

function playbookTone(status: SalesPlaybook["status"]): { color: string; backgroundColor: string } {
  if (status === "PUBLISHED") return { color: "#1E7B52", backgroundColor: "#E9F5EF" };
  if (status === "ARCHIVED") return { color: "#6B6459", backgroundColor: "#F1F1EF" };
  return { color: "#8A561B", backgroundColor: "#FFF8EE" };
}

function DetailFields({ fields }: { fields: KnowledgeCardDetailField[] }) {
  return (
    <dl className="flex flex-col gap-3 min-w-0">
      {fields.map((field) => (
        <div key={field.label} className="min-w-0">
          <dt className="text-[11px] font-medium text-[#9C9488]">{field.label}</dt>
          <dd
            className={`text-sm mt-0.5 leading-relaxed min-w-0 ${
              field.label === "Knowledge ID" ? "break-all" : "break-words"
            } [overflow-wrap:anywhere]`}
            style={field.label === "Knowledge ID" ? { fontFamily: "'IBM Plex Mono', monospace" } : undefined}
          >
            {field.values.length === 1 ? (
              field.values[0]
            ) : (
              <ul className="list-disc pl-4 flex flex-col gap-1">
                {field.values.map((value, index) => (
                  <li key={`${field.label}-${index}`} className="break-words [overflow-wrap:anywhere]">
                    {value}
                  </li>
                ))}
              </ul>
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function SalesPlaybookSettings({
  token,
  businessId,
}: {
  token: string;
  businessId: string;
}) {
  const [playbook, setPlaybook] = useState<SalesPlaybook | null>(null);
  const [versions, setVersions] = useState<SalesPlaybook[]>([]);
  const [cards, setCards] = useState<SalesKnowledgeCard[] | null>(null);
  const [filter, setFilter] = useState<KnowledgeCardFilter>("ALL");
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [reviewNotice, setReviewNotice] = useState<string | null>(null);
  const [openDetails, setOpenDetails] = useState<Record<string, boolean>>({});
  const [pendingReview, setPendingReview] = useState<PendingKnowledgeReview | null>(null);
  const confirmButtonRef = useRef<HTMLButtonElement | null>(null);
  const detailsToggleRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const reviewTriggerRefs = useRef<Record<string, Partial<Record<KnowledgeReviewAction, HTMLButtonElement | null>>>>({});
  const filterInputRefs = useRef<Partial<Record<KnowledgeCardFilter, HTMLInputElement | null>>>({});
  const filterRef = useRef<KnowledgeCardFilter>(filter);
  filterRef.current = filter;
  const pendingRestoreFocusRef = useRef<{
    cardKey: string;
    restore: KnowledgeReviewFallbackFocus;
    triggerAction: KnowledgeReviewAction | null;
  } | null>(null);
  const [restoreFocusEpoch, setRestoreFocusEpoch] = useState(0);
  const [importFileName, setImportFileName] = useState<string | null>(null);
  const [importRequest, setImportRequest] = useState<SalesKnowledgeImportRequest | null>(null);
  const [importParseError, setImportParseError] = useState<string | null>(null);
  const [importStatusIgnored, setImportStatusIgnored] = useState(false);
  const [importValidation, setImportValidation] = useState<SalesKnowledgeImportResponse | null>(null);
  const [importing, setImporting] = useState(false);
  const [validatingImport, setValidatingImport] = useState(false);
  const [importNotice, setImportNotice] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setDenied(false);
    setError(null);
    Promise.all([
      api.getActiveSalesPlaybook(token, businessId).catch((err: unknown) => {
        if (classifySalesError(err) === "playbook_empty") return null;
        throw err;
      }),
      api.listSalesPlaybooks(token, businessId),
      api.listSalesKnowledgeCards(token, businessId),
    ])
      .then(([active, list, knowledge]) => {
        if (cancelled) return;
        setPlaybook(active);
        setVersions(list.playbooks);
        setCards(knowledge.cards);
        setOpenDetails({});
        setPendingReview(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (classifySalesError(err) === "denied") setDenied(true);
        else setError(describeError(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, businessId]);

  useEffect(() => {
    if (!pendingReview) return;
    if (knowledgeReviewFocusTargetAfter("opened") === "confirm") {
      confirmButtonRef.current?.focus();
    }
  }, [pendingReview]);

  const visibleCards = useMemo(
    () => filterKnowledgeCards(cards ?? [], filter),
    [cards, filter],
  );
  const filterCounts = useMemo(
    () => knowledgeCardFilterCounts(cards ?? []),
    [cards],
  );

  const activeFilterInput = (activeFilter: KnowledgeCardFilter): HTMLInputElement | null => {
    return (
      filterInputRefs.current[activeFilter] ??
      (document.getElementById(knowledgeCardFilterInputId(activeFilter)) as HTMLInputElement | null)
    );
  };

  const scheduleReviewRestoreFocus = (
    cardKey: string,
    restore: KnowledgeReviewFallbackFocus,
    triggerAction: KnowledgeReviewAction | null = null,
  ) => {
    pendingRestoreFocusRef.current = { cardKey, restore, triggerAction };
    setRestoreFocusEpoch((epoch) => epoch + 1);
  };

  useEffect(() => {
    const pending = pendingRestoreFocusRef.current;
    if (!pending) return;
    const frame = requestAnimationFrame(() => {
      const intent = pendingRestoreFocusRef.current;
      if (!intent) return;
      const detailsToggle = detailsToggleRefs.current[intent.cardKey];
      const trigger = intent.triggerAction
        ? reviewTriggerRefs.current[intent.cardKey]?.[intent.triggerAction] ?? null
        : null;
      const target = resolveKnowledgeReviewRestoreFocus({
        restore: intent.restore,
        detailsToggle,
        trigger,
      });
      if (target === "trigger" && trigger?.isConnected) {
        trigger.focus();
      } else if (target === "details-toggle" && detailsToggle?.isConnected) {
        detailsToggle.focus();
      } else {
        activeFilterInput(intent.restore.filter)?.focus();
      }
      pendingRestoreFocusRef.current = null;
    });
    return () => cancelAnimationFrame(frame);
  }, [restoreFocusEpoch, visibleCards]);

  const toggleDetails = (card: SalesKnowledgeCard) => {
    const key = knowledgeCardKey(card);
    const nextOpen = !openDetails[key];
    setOpenDetails((current) => ({ ...current, [key]: nextOpen }));
    if (!nextOpen && isPendingReviewForCard(pendingReview, card)) {
      setPendingReview(null);
    }
  };

  const startReview = (
    card: SalesKnowledgeCard,
    action: "approve" | "reject",
    trigger: HTMLButtonElement | null,
  ) => {
    const pending = beginKnowledgeReview(card, Boolean(openDetails[knowledgeCardKey(card)]), action);
    if (!pending) return;
    reviewTriggerRefs.current[knowledgeCardKey(card)] = {
      ...reviewTriggerRefs.current[knowledgeCardKey(card)],
      [action]: trigger,
    };
    setReviewError(null);
    setReviewNotice(null);
    setPendingReview(pending);
  };

  const cancelReview = () => {
    if (reviewing) return;
    const pending = pendingReview;
    setPendingReview(null);
    if (!pending) return;
    scheduleReviewRestoreFocus(
      knowledgeCardKey({ knowledge_id: pending.knowledgeId, version: pending.version }),
      knowledgeReviewFallbackFocusTarget({
        event: "cancelled",
        cardVisibleInCurrentFilter: true,
        activeFilter: filterRef.current,
      }),
      pending.action,
    );
  };

  const review = async () => {
    if (!pendingReview || reviewing) return;
    const pending = pendingReview;
    setReviewing(true);
    setReviewError(null);
    setReviewNotice(null);
    try {
      const updated =
        pending.action === "approve"
          ? await api.approveSalesKnowledgeCard(
              token, businessId, pending.knowledgeId, pending.version,
            )
          : await api.rejectSalesKnowledgeCard(
              token, businessId, pending.knowledgeId, pending.version,
            );
      const nextCards = (cards ?? []).map((item) =>
        item.knowledge_id === updated.knowledge_id && item.version === updated.version ? updated : item,
      );
      const activeFilter = filterRef.current;
      setCards(nextCards);
      setPendingReview(null);
      setReviewNotice(knowledgeReviewLiveMessage("success", pending.action));
      scheduleReviewRestoreFocus(
        knowledgeCardKey(updated),
        knowledgeReviewFallbackFocusTarget({
          event: "succeeded",
          cardVisibleInCurrentFilter: isKnowledgeCardVisibleInFilter(nextCards, activeFilter, updated),
          activeFilter,
        }),
      );
    } catch (err) {
      if (err instanceof ApiError && err.code === "sales_knowledge_already_reviewed") {
        setReviewError(knowledgeReviewLiveMessage("error", pending.action, describeError(err)));
        setPendingReview(null);
        const reviewedCard = { knowledge_id: pending.knowledgeId, version: pending.version };
        const refreshed = await api.listSalesKnowledgeCards(token, businessId).catch(() => null);
        const nextCards = refreshed?.cards ?? cards ?? [];
        const activeFilter = filterRef.current;
        if (refreshed) {
          setCards(refreshed.cards);
          setOpenDetails((current) => retainOpenCardDetails(current, refreshed.cards));
        }
        scheduleReviewRestoreFocus(
          knowledgeCardKey(reviewedCard),
          knowledgeReviewFallbackFocusTarget({
            event: "conflict-refresh",
            cardVisibleInCurrentFilter: isKnowledgeCardVisibleInFilter(nextCards, activeFilter, reviewedCard),
            activeFilter,
          }),
        );
      } else if (classifySalesError(err) === "denied") {
        setDenied(true);
        setPendingReview(null);
      } else {
        setReviewError(knowledgeReviewLiveMessage("error", pending.action, describeError(err)));
      }
    } finally {
      setReviewing(false);
    }
  };

  const resetImport = () => {
    setImportRequest(null);
    setImportValidation(null);
    setImportParseError(null);
    setImportStatusIgnored(false);
    setImportNotice(null);
    setImportError(null);
  };

  const onImportFileChange = async (file: File | null) => {
    resetImport();
    setImportFileName(file?.name ?? null);
    if (!file) return;
    const parsed = parseKnowledgeImportJson(await file.text());
    if (!parsed.ok) {
      setImportParseError(parsed.error);
      return;
    }
    setImportRequest(parsed.request);
    setImportStatusIgnored(parsed.statusFieldIgnored);
  };

  const validateImport = async () => {
    if (!importRequest || validatingImport || importing) return;
    setValidatingImport(true);
    setImportError(null);
    setImportNotice(null);
    try {
      const result = await api.validateSalesKnowledgeImport(token, businessId, importRequest);
      setImportValidation(result);
      setImportNotice(knowledgeImportLiveMessage("validated"));
    } catch (err) {
      setImportValidation(null);
      if (classifySalesError(err) === "denied") setDenied(true);
      else setImportError(describeError(err));
    } finally {
      setValidatingImport(false);
    }
  };

  const commitImport = async () => {
    if (!importRequest || !canCommitKnowledgeImport(importValidation) || importing || validatingImport) return;
    setImporting(true);
    setImportError(null);
    setImportNotice(null);
    try {
      const result = await api.importSalesKnowledgeCards(token, businessId, importRequest);
      setImportValidation(result);
      setImportNotice(knowledgeImportLiveMessage("imported", result.checks.length));
      const knowledge = await api.listSalesKnowledgeCards(token, businessId);
      setCards(knowledge.cards);
      setOpenDetails((current) => retainOpenCardDetails(current, knowledge.cards));
      setImportRequest(null);
      setImportFileName(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      setImportStatusIgnored(false);
    } catch (err) {
      if (isKnowledgeImportVersionConflict(err)) {
        setImportError(knowledgeImportLiveMessage("conflict"));
        const [replay, knowledge] = await Promise.all([
          api.validateSalesKnowledgeImport(token, businessId, importRequest).catch(() => null),
          api.listSalesKnowledgeCards(token, businessId).catch(() => null),
        ]);
        if (replay) setImportValidation(replay);
        if (knowledge) {
          setCards(knowledge.cards);
          setOpenDetails((current) => retainOpenCardDetails(current, knowledge.cards));
        }
      } else if (classifySalesError(err) === "denied") {
        setDenied(true);
      } else {
        setImportError(describeError(err));
      }
    } finally {
      setImporting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-[#6B6459] py-8" role="status">
        <Loader2 size={16} className="animate-spin" /> Loading sales playbook…
      </div>
    );
  }

  if (denied) {
    return (
      <div className="px-4 py-3 rounded-lg text-sm" role="alert" style={{ backgroundColor: "#FBEBE9", color: "#8A3225" }}>
        You don’t have permission to view the sales playbook for this business.
      </div>
    );
  }

  if (error) {
    return (
      <div className="px-4 py-3 rounded-lg text-sm" role="alert" style={{ backgroundColor: "#FBEBE9", color: "#8A3225" }}>
        {error}
      </div>
    );
  }

  return (
    <div className="min-w-0 overflow-x-hidden">
      <p className="text-sm text-[#6B6459] mb-6 leading-relaxed">
        The sales playbook is the approved conversation method. It is separate from case status
        (qualification, booking, won). AI may phrase an approved move; it does not set prices,
        discounts, or bookings.
      </p>

      {playbook ? (
        <div className="rounded-2xl border p-4 sm:p-5 mb-6 min-w-0" style={{ borderColor: "#E7E5DE" }}>
          <div className="flex items-start justify-between gap-3 flex-wrap min-w-0">
            <div className="flex items-start gap-3 min-w-0">
              <span className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0 text-white" style={{ backgroundColor: "#B87333" }}>
                <BookOpen size={18} />
              </span>
              <div className="min-w-0">
                <h2 className="text-base font-semibold">Active playbook</h2>
                <p className="text-sm text-[#6B6459] mt-0.5 break-words" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>
                  Version {playbook.version}
                  {playbook.published_at ? ` · published ${formatRelativeTime(playbook.published_at)}` : ""}
                </p>
              </div>
            </div>
            <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium" style={playbookTone(playbook.status)}>
              {PLAYBOOK_STATUS_LABELS[playbook.status]}
            </span>
          </div>
          <p className="text-xs text-[#9C9488] mt-4 leading-relaxed">
            Read-only. A published playbook cannot be edited here. New methods are published as a new version.
          </p>
        </div>
      ) : (
        <div className="rounded-2xl border p-4 sm:p-5 mb-6" style={{ borderColor: "#E7E5DE", backgroundColor: "#FAFAF7" }}>
          <h2 className="text-base font-semibold">No published playbook</h2>
          <p className="text-sm text-[#6B6459] mt-1 leading-relaxed">
            There is no live sales playbook for this business yet. Draft or archived versions, if any, are listed below. The engine will not use a draft as the live method.
          </p>
        </div>
      )}

      {versions.length > 0 && (
        <div className="mb-8 min-w-0">
          <div className="text-sm font-semibold mb-3">Playbook versions</div>
          <div className="flex flex-col gap-2">
            {versions.map((item) => (
              <div key={item.version} className="flex items-center justify-between gap-3 flex-wrap px-3 py-2.5 rounded-xl border border-[#E7E5DE] text-sm min-w-0">
                <span style={{ fontFamily: "'IBM Plex Mono', monospace" }}>v{item.version}</span>
                <span className="text-xs px-2 py-0.5 rounded-full" style={playbookTone(item.status)}>
                  {PLAYBOOK_STATUS_LABELS[item.status]}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="text-sm font-semibold mb-2">Knowledge cards</div>
      <p className="text-sm text-[#6B6459] mb-4 leading-relaxed">
        Only approved cards may be used in a customer reply. Candidates stay unused until you approve or reject them.
      </p>

      <div className="rounded-2xl border p-4 sm:p-5 mb-6 min-w-0" style={{ borderColor: "#E7E5DE" }}>
        <h3 className="text-sm font-semibold">Import JSON</h3>
        <p className="text-sm text-[#6B6459] mt-1 leading-relaxed">{KNOWLEDGE_IMPORT_CANDIDATE_NOTICE}</p>
        {importStatusIgnored && (
          <p className="text-xs text-[#8A561B] mt-2 leading-relaxed">
            A status field in the file was ignored. Imported cards are always Candidate.
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2 mt-4">
          <label
            htmlFor="knowledge-import-file"
            className={`text-xs font-medium px-3 py-2 rounded-lg border border-[#E7E5DE] flex items-center gap-1.5 cursor-pointer ${FOCUS_RING} has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-[#B87333] has-[:focus-visible]:ring-offset-2`}
          >
            <Upload size={12} aria-hidden="true" />
            Choose JSON file
            <input
              id="knowledge-import-file"
              ref={fileInputRef}
              type="file"
              accept="application/json,.json"
              className="sr-only"
              onChange={(event) => {
                void onImportFileChange(event.target.files?.[0] ?? null);
              }}
            />
          </label>
          <span className="text-xs text-[#6B6459] break-all [overflow-wrap:anywhere] min-w-0">
            {importFileName ?? "No file selected"}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2 mt-3">
          <button
            type="button"
            disabled={!importRequest || validatingImport || importing}
            aria-busy={validatingImport}
            onClick={() => void validateImport()}
            className={`text-xs font-medium text-white px-3 py-2 rounded-lg flex items-center gap-1.5 disabled:opacity-50 ${FOCUS_RING}`}
            style={{ backgroundColor: "#151515" }}
          >
            {validatingImport && <Loader2 size={12} className="animate-spin" aria-hidden="true" />}
            Check import
          </button>
          <button
            type="button"
            disabled={!canCommitKnowledgeImport(importValidation) || importing || validatingImport}
            aria-busy={importing}
            onClick={() => void commitImport()}
            className={`text-xs font-medium px-3 py-2 rounded-lg border border-[#E7E5DE] flex items-center gap-1.5 disabled:opacity-50 ${FOCUS_RING}`}
          >
            {importing && <Loader2 size={12} className="animate-spin" aria-hidden="true" />}
            Import as candidates
          </button>
        </div>
        <div
          className={importNotice ? "mt-3 px-3 py-2 rounded-lg text-xs" : "sr-only"}
          role="status"
          aria-live="polite"
          aria-atomic="true"
          style={importNotice ? { backgroundColor: "#E9F5EF", color: "#1E7B52" } : undefined}
        >
          {importNotice ?? ""}
        </div>
        <div role="alert" aria-live="assertive" aria-atomic="true">
          {(importParseError || importError) && (
            <div className="mt-3 px-3 py-2 rounded-lg text-xs" style={{ backgroundColor: "#FBEBE9", color: "#8A3225" }}>
              {importParseError || importError}
            </div>
          )}
        </div>
        {importValidation && (
          <ul className="mt-3 flex flex-col gap-1.5 min-w-0" aria-label="Import validation results">
            {importValidation.checks.map((check) => (
              <li
                key={`${check.knowledge_id}:${check.version}`}
                className="text-xs leading-relaxed min-w-0 break-words [overflow-wrap:anywhere]"
              >
                <span className="break-all" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>
                  {check.knowledge_id}
                </span>
                {` v${check.version} — ${knowledgeImportCheckLabel(check)}`}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div role="radiogroup" aria-label="Filter knowledge cards" className="flex flex-wrap gap-1.5 mb-4">
        {KNOWLEDGE_CARD_FILTER_OPTIONS.map((item) => {
          const inputId = knowledgeCardFilterInputId(item.key);
          const selected = filter === item.key;
          const count = cards && cards.length > 0 ? filterCounts[item.key] : null;
          return (
            <label
              key={item.key}
              htmlFor={inputId}
              className={FILTER_PILL}
              style={{
                borderColor: selected ? "#151515" : "#E7E5DE",
                backgroundColor: selected ? "#151515" : "#fff",
                color: selected ? "#fff" : "#6B6459",
              }}
            >
              <input
                type="radio"
                id={inputId}
                ref={(node) => {
                  filterInputRefs.current[item.key] = node;
                }}
                name={KNOWLEDGE_CARD_FILTER_GROUP_NAME}
                value={item.key}
                checked={selected}
                className="sr-only"
                onChange={(event) => {
                  if (isKnowledgeCardFilter(event.target.value)) setFilter(event.target.value);
                }}
              />
              {knowledgeCardFilterAccessibleLabel(item.label, count)}
            </label>
          );
        })}
      </div>

      <div
        className={reviewNotice ? "mb-4 px-4 py-3 rounded-lg text-sm" : "sr-only"}
        role="status"
        aria-live="polite"
        aria-atomic="true"
        style={reviewNotice ? { backgroundColor: "#E9F5EF", color: "#1E7B52" } : undefined}
      >
        {reviewNotice ?? ""}
      </div>
      <div role="alert" aria-live="assertive" aria-atomic="true">
        {reviewError && (
          <div className="mb-4 px-4 py-3 rounded-lg text-sm" style={{ backgroundColor: "#FBEBE9", color: "#8A3225" }}>
            {reviewError}
          </div>
        )}
      </div>

      {visibleCards.length === 0 ? (
        <p className="text-sm text-[#9C9488] py-4">
          {cards && cards.length > 0 ? "No cards match this filter." : "No knowledge cards yet."}
        </p>
      ) : (
        <div className="flex flex-col gap-3 min-w-0">
          {visibleCards.map((card) => {
            const source = knowledgeSourceLabel(card.source);
            const key = knowledgeCardKey(card);
            const detailsOpen = Boolean(openDetails[key]);
            const detailsId = knowledgeCardDomId("knowledge-details", card);
            const confirmTitleId = knowledgeCardDomId("knowledge-review-title", card);
            const confirmWarningId = knowledgeCardDomId("knowledge-review-warning", card);
            const details = partitionKnowledgeCardDetails(knowledgeCardDetailFields(card));
            const pendingHere = isPendingReviewForCard(pendingReview, card) ? pendingReview : null;
            const confirmation = pendingHere ? knowledgeReviewConfirmation(pendingHere) : null;
            const showReviewActions = canConfirmKnowledgeReview(card.status, detailsOpen) && !pendingHere;
            return (
              <article key={key} className="p-4 rounded-xl border border-[#E7E5DE] min-w-0 overflow-hidden" aria-busy={Boolean(pendingHere && reviewing)}>
                <div className="flex items-start justify-between gap-3 flex-wrap min-w-0">
                  <div className="min-w-0 flex-1">
                    <h3 className="text-sm font-semibold leading-relaxed break-words [overflow-wrap:anywhere]">
                      {card.principle}
                    </h3>
                    <p
                      className="text-xs text-[#6B6459] mt-1 break-all [overflow-wrap:anywhere]"
                      style={{ fontFamily: "'IBM Plex Mono', monospace" }}
                    >
                      {card.knowledge_id}
                    </p>
                    {(source.title || source.location) && (
                      <p className="text-xs text-[#6B6459] mt-0.5 break-words [overflow-wrap:anywhere]">
                        {[source.title, source.location].filter(Boolean).join(" · ")}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-[11px] text-[#9C9488]" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>
                      v{card.version}
                    </span>
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium" style={statusTone(card.status)}>
                      {KNOWLEDGE_STATUS_LABELS[card.status]}
                    </span>
                  </div>
                </div>

                <button
                  type="button"
                  id={knowledgeCardDomId("knowledge-details-toggle", card)}
                  ref={(node) => {
                    detailsToggleRefs.current[key] = node;
                  }}
                  aria-expanded={detailsOpen}
                  aria-controls={detailsId}
                  onClick={() => toggleDetails(card)}
                  className={`mt-3 text-xs font-medium text-[#B87333] rounded-sm ${FOCUS_RING}`}
                >
                  {detailsOpen ? "Hide details" : "View details"}
                </button>

                {detailsOpen && (
                  <div id={detailsId} className="mt-4 min-w-0">
                    <div className="rounded-lg p-3 sm:p-4 min-w-0 overflow-hidden" style={{ backgroundColor: "#FAFAF7" }}>
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-[#9C9488] mb-3">Card</p>
                      <DetailFields fields={details.identity} />
                    </div>
                    <div className="rounded-lg p-3 sm:p-4 mt-3 min-w-0 overflow-hidden" style={{ backgroundColor: "#FAFAF7" }}>
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-[#9C9488] mb-3">Policy rules</p>
                      <DetailFields fields={details.policy} />
                    </div>
                  </div>
                )}

                {showReviewActions && (
                  <div className="flex flex-wrap items-center gap-2 mt-4">
                    <button
                      type="button"
                      ref={(node) => {
                        reviewTriggerRefs.current[key] = {
                          ...reviewTriggerRefs.current[key],
                          approve: node,
                        };
                      }}
                      disabled={reviewing}
                      onClick={(event) => startReview(card, "approve", event.currentTarget)}
                      className={`text-xs font-medium text-white px-3 py-2 rounded-lg flex items-center gap-1.5 disabled:opacity-50 ${FOCUS_RING}`}
                      style={{ backgroundColor: "#151515" }}
                    >
                      <Check size={12} />
                      Approve
                    </button>
                    <button
                      type="button"
                      ref={(node) => {
                        reviewTriggerRefs.current[key] = {
                          ...reviewTriggerRefs.current[key],
                          reject: node,
                        };
                      }}
                      disabled={reviewing}
                      onClick={(event) => startReview(card, "reject", event.currentTarget)}
                      className={`text-xs font-medium px-3 py-2 rounded-lg border border-[#E7E5DE] flex items-center gap-1.5 disabled:opacity-50 ${FOCUS_RING}`}
                    >
                      <X size={12} />
                      Reject
                    </button>
                  </div>
                )}

                {confirmation && (
                  <div
                    role={KNOWLEDGE_REVIEW_CONFIRMATION_ROLE}
                    aria-labelledby={confirmTitleId}
                    aria-describedby={confirmWarningId}
                    className="mt-4 p-3 rounded-lg border min-w-0"
                    style={{ borderColor: "#E8CFAF", backgroundColor: "#FFF8EE" }}
                    onKeyDown={(event) => {
                      if (knowledgeReviewConfirmationCancelsOnKey(event.key, reviewing)) {
                        event.preventDefault();
                        cancelReview();
                      }
                    }}
                  >
                    <p id={confirmTitleId} className="text-sm break-words [overflow-wrap:anywhere]">
                      Confirm {confirmation.actionLabel} of knowledge card{" "}
                      <span className="break-all" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>
                        {confirmation.knowledgeId}
                      </span>
                      {" "}version {confirmation.version}.
                    </p>
                    <p id={confirmWarningId} className="text-xs text-[#8A561B] mt-1.5 leading-relaxed">
                      {confirmation.warning}
                    </p>
                    <div className="flex flex-wrap items-center gap-2 mt-3">
                      <button
                        type="button"
                        ref={pendingHere ? confirmButtonRef : undefined}
                        disabled={reviewing}
                        aria-busy={reviewing}
                        onClick={review}
                        className={`text-xs font-medium text-white px-3 py-2 rounded-lg flex items-center gap-1.5 disabled:opacity-50 ${FOCUS_RING}`}
                        style={{ backgroundColor: "#151515" }}
                      >
                        {reviewing && <Loader2 size={12} className="animate-spin" aria-hidden="true" />}
                        {knowledgeReviewPendingLabel(confirmation.action, reviewing)}
                      </button>
                      <button
                        type="button"
                        disabled={reviewing}
                        onClick={cancelReview}
                        className={`text-xs font-medium px-3 py-2 rounded-lg border border-[#E7E5DE] disabled:opacity-50 ${FOCUS_RING}`}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}

                {!canReviewKnowledgeCard(card.status) && card.reviewed_at && (
                  <p className="text-[11px] text-[#9C9488] mt-3">
                    Reviewed {formatRelativeTime(card.reviewed_at)}
                  </p>
                )}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
