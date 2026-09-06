import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { describeError } from "../auth/AuthContext";
import {
  api,
  type SalesCaseContext,
  type SalesShadowEvaluation,
  type SalesShadowResult,
  type SalesTurn,
} from "../api/client";
import { formatRelativeTime } from "./Shared";
import {
  activeObjection,
  classifySalesError,
  latestSalesTurnForConversation,
  reasonCodeLabel,
  salesMoveLabel,
  salesStageLabel,
} from "../lib/salesCopy";
import {
  SALES_SHADOW_EVALUATION_LABELS,
  SALES_SHADOW_EVALUATION_VALUES,
  SHADOW_NOT_SENT_NOTICE,
  canSubmitShadowEvaluation,
  isSalesShadowEvaluation,
  isShadowAlreadyEvaluatedConflict,
  shadowEvaluationLiveMessage,
  shadowResultsForConversation,
  shadowSalesUiCopy,
  shadowSalesUiKindFromStatus,
} from "../lib/salesShadowUi";

/**
 * Conversation sales context for a linked case, including shadow comparison
 * results for this conversation only. Sales stage is not ProcessState.
 * Shadow replies are never sent to the customer from this panel.
 */

const FOCUS_RING =
  "outline-none focus-visible:ring-2 focus-visible:ring-[#B87333] focus-visible:ring-offset-2";

function Field({ label, children }: { label: string; children: string | null | undefined }) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] font-medium text-[#9C9488] mb-0.5">{label}</div>
      <div className="text-sm break-words [overflow-wrap:anywhere]">
        {children?.trim() ? children : "Not captured yet"}
      </div>
    </div>
  );
}

function WrappingIdList({ ids }: { ids: readonly string[] }) {
  if (ids.length === 0) return <span>None</span>;
  return (
    <ul className="flex flex-col gap-1 mt-1 min-w-0">
      {ids.map((id) => (
        <li
          key={id}
          className="break-all [overflow-wrap:anywhere]"
          style={{ fontFamily: "'IBM Plex Mono', monospace" }}
        >
          {id}
        </li>
      ))}
    </ul>
  );
}

function shadowTone(kind: ReturnType<typeof shadowSalesUiKindFromStatus>): {
  color: string;
  backgroundColor: string;
} {
  const copy = shadowSalesUiCopy(kind);
  if (copy.tone === "success") return { color: "#1E7B52", backgroundColor: "#E9F5EF" };
  if (copy.tone === "warning") return { color: "#8A561B", backgroundColor: "#FFF8EE" };
  if (copy.tone === "danger") return { color: "#8A3225", backgroundColor: "#FBEBE9" };
  if (copy.tone === "info") return { color: "#2F5D8A", backgroundColor: "#EEF4FA" };
  return { color: "#6B6459", backgroundColor: "#F1F1EF" };
}

function ShadowResultCard({
  result,
  evaluating,
  alreadySubmitted,
  selectedEvaluation,
  onSelectEvaluation,
  onSubmitEvaluation,
}: {
  result: SalesShadowResult;
  evaluating: boolean;
  alreadySubmitted: boolean;
  selectedEvaluation: SalesShadowEvaluation | "";
  onSelectEvaluation: (value: SalesShadowEvaluation) => void;
  onSubmitEvaluation: () => void;
}) {
  const kind = shadowSalesUiKindFromStatus(result.status);
  const copy = shadowSalesUiCopy(kind);
  const tone = shadowTone(kind);
  const canEvaluate = canSubmitShadowEvaluation(result, evaluating || alreadySubmitted);
  const formId = `shadow-eval-${result.shadow_id}`;
  const titleId = `shadow-title-${result.shadow_id}`;

  return (
    <article
      className="rounded-lg border border-[#E7E5DE] p-3 min-w-0 overflow-hidden"
      aria-labelledby={titleId}
      aria-busy={evaluating}
    >
      <div className="flex items-start justify-between gap-2 flex-wrap min-w-0">
        <h4 id={titleId} className="text-xs font-semibold min-w-0 break-words [overflow-wrap:anywhere]">
          {copy.title}
        </h4>
        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium shrink-0" style={tone}>
          {result.status.replace(/_/g, " ")}
        </span>
      </div>
      <p className="text-[11px] text-[#6B6459] mt-1 leading-relaxed">{copy.description}</p>
      <p className="text-[11px] font-medium mt-2 leading-relaxed" style={{ color: "#8A561B" }}>
        {SHADOW_NOT_SENT_NOTICE}
      </p>

      <dl className="flex flex-col gap-2 mt-3 min-w-0">
        <div className="min-w-0">
          <dt className="text-[11px] font-medium text-[#9C9488]">Approved move</dt>
          <dd className="text-xs mt-0.5 break-words [overflow-wrap:anywhere]">{salesMoveLabel(result.approved_move)}</dd>
        </div>
        <div className="min-w-0">
          <dt className="text-[11px] font-medium text-[#9C9488]">Proposed shadow reply</dt>
          <dd className="text-xs mt-0.5 break-words [overflow-wrap:anywhere]">
            {result.proposed_response_text?.trim() || "None"}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-[11px] font-medium text-[#9C9488]">Live reply the customer received</dt>
          <dd className="text-xs mt-0.5 break-words [overflow-wrap:anywhere]">
            {result.delivered_response_text?.trim() || "None recorded"}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-[11px] font-medium text-[#9C9488]">Violations</dt>
          <dd className="text-xs mt-0.5 min-w-0">
            {result.violations.length === 0 ? (
              "None"
            ) : (
              <ul className="list-disc pl-4 flex flex-col gap-1">
                {result.violations.map((item, index) => (
                  <li key={`${result.shadow_id}-v-${index}`} className="break-words [overflow-wrap:anywhere]">
                    {item}
                  </li>
                ))}
              </ul>
            )}
          </dd>
        </div>
      </dl>

      <div className="pt-3 mt-3 border-t border-[#F0EFE9] min-w-0">
        <div className="text-[11px] font-medium text-[#9C9488] mb-2">Provenance</div>
        <div className="flex flex-col gap-2 text-xs text-[#6B6459] min-w-0">
          <div className="min-w-0">
            <span className="font-medium text-[#151515]">Shadow ID</span>
            <div className="break-all [overflow-wrap:anywhere] mt-1" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>
              {result.shadow_id}
            </div>
          </div>
          <div className="min-w-0">
            <span className="font-medium text-[#151515]">Source message</span>
            <div className="break-all [overflow-wrap:anywhere] mt-1" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>
              {result.source_message_id}
            </div>
          </div>
          <div className="min-w-0">
            <span className="font-medium text-[#151515]">Knowledge IDs</span>
            <WrappingIdList ids={result.knowledge_ids} />
          </div>
          <div className="min-w-0">
            <span className="font-medium text-[#151515]">Business facts</span>
            <WrappingIdList ids={result.business_fact_ids} />
          </div>
          <div className="min-w-0">
            <span className="font-medium text-[#151515]">Customer evidence IDs</span>
            <WrappingIdList ids={result.customer_evidence_ids} />
          </div>
          {(result.prompt_version || result.model_name) && (
            <p className="text-[11px] break-words [overflow-wrap:anywhere]">
              {[result.prompt_version, result.model_name].filter(Boolean).join(" · ")}
            </p>
          )}
        </div>
      </div>

      {result.status === "EVALUATED" && result.evaluation ? (
        <div className="mt-3 px-3 py-2 rounded-lg min-w-0" style={{ backgroundColor: "#EEF4FA", color: "#2F5D8A" }}>
          <div className="text-[11px] font-semibold">Recorded evaluation</div>
          <p className="text-xs mt-0.5 break-words [overflow-wrap:anywhere]">
            {SALES_SHADOW_EVALUATION_LABELS[result.evaluation]}
          </p>
          <p className="text-[11px] mt-1 break-all [overflow-wrap:anywhere]">
            {result.evaluated_by ?? ""}
            {result.evaluated_at ? ` · ${formatRelativeTime(result.evaluated_at)}` : ""}
          </p>
        </div>
      ) : (
        <fieldset className="mt-3 min-w-0" disabled={!canEvaluate}>
          <legend className="text-[11px] font-medium text-[#9C9488] mb-2">Human evaluation</legend>
          <div role="radiogroup" aria-label="Shadow evaluation" className="flex flex-col gap-1.5">
            {SALES_SHADOW_EVALUATION_VALUES.map((value) => {
              const inputId = `${formId}-${value}`;
              return (
                <label
                  key={value}
                  htmlFor={inputId}
                  className={`flex items-start gap-2 text-xs rounded-lg px-2 py-1.5 border border-[#E7E5DE] min-w-0 ${FOCUS_RING} has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-[#B87333]`}
                >
                  <input
                    type="radio"
                    id={inputId}
                    name={formId}
                    value={value}
                    checked={selectedEvaluation === value}
                    disabled={!canEvaluate}
                    onChange={(event) => {
                      if (isSalesShadowEvaluation(event.target.value)) onSelectEvaluation(event.target.value);
                    }}
                    className="mt-0.5 accent-[#B87333]"
                  />
                  <span className="break-words [overflow-wrap:anywhere]">{SALES_SHADOW_EVALUATION_LABELS[value]}</span>
                </label>
              );
            })}
          </div>
          <button
            type="button"
            disabled={!canEvaluate || selectedEvaluation === ""}
            aria-busy={evaluating}
            onClick={onSubmitEvaluation}
            className={`mt-2 text-xs font-medium text-white px-3 py-2 rounded-lg disabled:opacity-50 ${FOCUS_RING}`}
            style={{ backgroundColor: "#151515" }}
          >
            {evaluating ? "Recording…" : "Record evaluation"}
          </button>
        </fieldset>
      )}
    </article>
  );
}

export function ConversationSalesPanel({
  token,
  businessId,
  caseId,
  conversationId,
}: {
  token: string;
  businessId: string;
  caseId: string | null;
  conversationId: string;
}) {
  const [context, setContext] = useState<SalesCaseContext | null>(null);
  const [turns, setTurns] = useState<SalesTurn[]>([]);
  const [shadows, setShadows] = useState<SalesShadowResult[]>([]);
  const [loading, setLoading] = useState(Boolean(caseId));
  const [shadowLoading, setShadowLoading] = useState(Boolean(caseId));
  const [denied, setDenied] = useState(false);
  const [shadowDenied, setShadowDenied] = useState(false);
  const [empty, setEmpty] = useState(!caseId);
  const [error, setError] = useState<string | null>(null);
  const [shadowError, setShadowError] = useState<string | null>(null);
  const [evaluatingId, setEvaluatingId] = useState<string | null>(null);
  const [evaluationChoice, setEvaluationChoice] = useState<Record<string, SalesShadowEvaluation | "">>({});
  const [evaluationNotice, setEvaluationNotice] = useState<string | null>(null);
  const [evaluationError, setEvaluationError] = useState<string | null>(null);
  const [submittedIds, setSubmittedIds] = useState<Record<string, true>>({});

  const refreshShadowResults = async () => {
    if (!caseId) return;
    const list = await api.listCaseSalesShadowResults(token, businessId, caseId);
    setShadows(list.results);
  };

  useEffect(() => {
    let cancelled = false;
    setContext(null);
    setTurns([]);
    setShadows([]);
    setDenied(false);
    setShadowDenied(false);
    setError(null);
    setShadowError(null);
    setEvaluationNotice(null);
    setEvaluationError(null);
    setEvaluationChoice({});
    setSubmittedIds({});
    if (!caseId) {
      setEmpty(true);
      setLoading(false);
      setShadowLoading(false);
      return;
    }
    setEmpty(false);
    setLoading(true);
    setShadowLoading(true);
    Promise.all([
      api.getCaseSalesContext(token, businessId, caseId),
      api.listCaseSalesTurns(token, businessId, caseId),
    ])
      .then(([sales, history]) => {
        if (cancelled) return;
        setContext(sales);
        setTurns(history.turns);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const kind = classifySalesError(err);
        if (kind === "denied") setDenied(true);
        else if (kind === "profile_empty" || kind === "case_missing") setEmpty(true);
        else setError(describeError(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    api
      .listCaseSalesShadowResults(token, businessId, caseId)
      .then((list) => {
        if (cancelled) return;
        setShadows(list.results);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const kind = classifySalesError(err);
        if (kind === "denied") setShadowDenied(true);
        else if (kind === "case_missing") setShadows([]);
        else setShadowError(describeError(err));
      })
      .finally(() => {
        if (!cancelled) setShadowLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token, businessId, caseId]);

  const objection = context ? activeObjection(context.objections) : null;
  const latest = latestSalesTurnForConversation(turns, conversationId);
  const conversationShadows = useMemo(
    () => shadowResultsForConversation(shadows, conversationId),
    [shadows, conversationId],
  );

  const submitEvaluation = async (result: SalesShadowResult) => {
    if (!caseId || evaluatingId) return;
    const choice = evaluationChoice[result.shadow_id];
    if (!choice || !canSubmitShadowEvaluation(result, Boolean(submittedIds[result.shadow_id]))) return;
    setEvaluatingId(result.shadow_id);
    setEvaluationError(null);
    setEvaluationNotice(null);
    setSubmittedIds((current) => ({ ...current, [result.shadow_id]: true }));
    try {
      const updated = await api.evaluateSalesShadowResult(
        token, businessId, caseId, result.shadow_id, choice,
      );
      setShadows((current) =>
        current.map((item) => (item.shadow_id === updated.shadow_id ? updated : item)),
      );
      setEvaluationNotice(shadowEvaluationLiveMessage("success"));
    } catch (err) {
      if (isShadowAlreadyEvaluatedConflict(err)) {
        setEvaluationNotice(shadowEvaluationLiveMessage("conflict"));
        await refreshShadowResults().catch(() => undefined);
      } else if (classifySalesError(err) === "denied") {
        setShadowDenied(true);
      } else {
        setSubmittedIds((current) => {
          const next = { ...current };
          delete next[result.shadow_id];
          return next;
        });
        setEvaluationError(describeError(err));
      }
    } finally {
      setEvaluatingId(null);
    }
  };

  return (
    <div className="rounded-xl border border-[#E7E5DE] bg-white p-4 min-w-0 overflow-x-hidden">
      <div className="text-xs font-semibold mb-1">Sales conversation</div>
      <p className="text-[11px] text-[#9C9488] mb-3 leading-relaxed">
        Sales stage is conversation progress. Case status on the right is the business commitment
        (qualification, booking, won) and is decided separately.
      </p>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-[#6B6459] py-2" role="status">
          <Loader2 size={14} className="animate-spin" /> Loading sales context…
        </div>
      )}

      {denied && (
        <div className="px-3 py-2 rounded-lg text-xs" role="alert" style={{ backgroundColor: "#FBEBE9", color: "#8A3225" }}>
          You don’t have permission to view sales context for this case.
        </div>
      )}

      {error && (
        <div className="px-3 py-2 rounded-lg text-xs" role="alert" aria-live="assertive" style={{ backgroundColor: "#FBEBE9", color: "#8A3225" }}>
          {error}
        </div>
      )}

      {!loading && !denied && !error && empty && (
        <p className="text-sm text-[#6B6459]">
          {caseId
            ? "No sales conversation profile yet for this case."
            : "This conversation isn’t linked to a case, so there is no sales profile."}
        </p>
      )}

      {!loading && context && (
        <div className="flex flex-col gap-3 min-w-0">
          <Field label="Sales stage">{salesStageLabel(context.stage)}</Field>
          <Field label="Customer goal">{context.customer_goal}</Field>
          <Field label="Active objection">
            {objection
              ? `${objection.objection_type.replace(/_/g, " ").toLowerCase()} · ${objection.status.replace(/_/g, " ").toLowerCase()}${objection.cause ? ` · ${objection.cause}` : ""}`
              : null}
          </Field>
          {objection?.evidence_excerpt && (
            <p className="text-xs text-[#6B6459] -mt-2 break-words [overflow-wrap:anywhere]">
              “{objection.evidence_excerpt}”
            </p>
          )}
          <Field label="Last approved move">{context.last_move ? salesMoveLabel(context.last_move) : null}</Field>
          <div className="min-w-0">
            <div className="text-[11px] font-medium text-[#9C9488] mb-0.5">Next approved action</div>
            <div className="text-sm font-medium break-words">{salesMoveLabel(context.next_approved_action)}</div>
            <p className="text-xs text-[#6B6459] mt-0.5 break-words [overflow-wrap:anywhere]">
              {reasonCodeLabel(context.next_action_reason)}
            </p>
            <p className="text-[11px] text-[#9C9488] mt-1 leading-relaxed">
              Chosen by sales policy, not by the model. This does not change price, discount, or booking rules.
            </p>
          </div>
          {context.requires_human && (
            <div className="px-3 py-2 rounded-lg min-w-0" style={{ backgroundColor: "#FFF8EE", color: "#8A561B" }}>
              <div className="text-[11px] font-semibold">Needs human review</div>
              <p className="text-xs mt-0.5 break-words [overflow-wrap:anywhere]">
                {context.human_review_reason
                  ? reasonCodeLabel(context.human_review_reason)
                  : "Policy handed this turn to you."}
              </p>
            </div>
          )}

          <div className="pt-3 border-t border-[#F0EFE9] min-w-0">
            <div className="text-[11px] font-medium text-[#9C9488] mb-2">Provenance of the latest conversation turn</div>
            {!latest ? (
              <p className="text-xs text-[#9C9488]">No sales turns recorded for this conversation yet.</p>
            ) : (
              <div className="flex flex-col gap-2 text-xs text-[#6B6459] min-w-0">
                <div className="min-w-0">
                  <span className="font-medium text-[#151515]">Knowledge IDs</span>
                  <WrappingIdList ids={latest.knowledge_ids} />
                </div>
                <div className="min-w-0">
                  <span className="font-medium text-[#151515]">Business facts</span>
                  <WrappingIdList ids={latest.business_fact_ids} />
                </div>
                <div className="min-w-0">
                  <span className="font-medium text-[#151515]">Customer evidence</span>
                  {latest.customer_evidence.length === 0 ? (
                    <div className="mt-1">None</div>
                  ) : (
                    <ul className="flex flex-col gap-1 mt-1">
                      {latest.customer_evidence.map((item, index) => (
                        <li key={`${item.source_message_id}-${index}`} className="break-words [overflow-wrap:anywhere]">
                          “{item.excerpt}”
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {caseId && (
        <div className="pt-3 mt-3 border-t border-[#F0EFE9] min-w-0">
          <div className="text-[11px] font-medium text-[#9C9488] mb-1">Shadow comparison</div>
          <p className="text-[11px] text-[#6B6459] mb-3 leading-relaxed">
            Drafts below are for staff comparison on this conversation only. They are not sent to the customer.
          </p>

          {shadowLoading && (
            <div className="flex items-center gap-2 text-sm text-[#6B6459] py-2" role="status">
              <Loader2 size={14} className="animate-spin" /> Loading shadow results…
            </div>
          )}

          {shadowDenied && (
            <div className="px-3 py-2 rounded-lg text-xs" role="alert" style={{ backgroundColor: "#FBEBE9", color: "#8A3225" }}>
              You don’t have permission to view shadow comparisons for this case.
            </div>
          )}

          {shadowError && (
            <div className="px-3 py-2 rounded-lg text-xs" role="alert" aria-live="assertive" style={{ backgroundColor: "#FBEBE9", color: "#8A3225" }}>
              {shadowError}
            </div>
          )}

          <div
            className={evaluationNotice ? "mb-3 px-3 py-2 rounded-lg text-xs" : "sr-only"}
            role="status"
            aria-live="polite"
            aria-atomic="true"
            style={evaluationNotice ? { backgroundColor: "#E9F5EF", color: "#1E7B52" } : undefined}
          >
            {evaluationNotice ?? ""}
          </div>
          <div role="alert" aria-live="assertive" aria-atomic="true">
            {evaluationError && (
              <div className="mb-3 px-3 py-2 rounded-lg text-xs" style={{ backgroundColor: "#FBEBE9", color: "#8A3225" }}>
                {evaluationError}
              </div>
            )}
          </div>

          {!shadowLoading && !shadowDenied && !shadowError && conversationShadows.length === 0 && (
            <p className="text-xs text-[#9C9488]">{shadowSalesUiCopy("none").description}</p>
          )}

          {!shadowLoading && conversationShadows.length > 0 && (
            <div className="flex flex-col gap-3 min-w-0">
              {conversationShadows.map((result) => (
                <ShadowResultCard
                  key={result.shadow_id}
                  result={result}
                  evaluating={evaluatingId === result.shadow_id}
                  alreadySubmitted={Boolean(submittedIds[result.shadow_id])}
                  selectedEvaluation={evaluationChoice[result.shadow_id] ?? ""}
                  onSelectEvaluation={(value) => {
                    if (!canSubmitShadowEvaluation(result, Boolean(submittedIds[result.shadow_id]))) return;
                    setEvaluationChoice((current) => ({ ...current, [result.shadow_id]: value }));
                  }}
                  onSubmitEvaluation={() => {
                    void submitEvaluation(result);
                  }}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
