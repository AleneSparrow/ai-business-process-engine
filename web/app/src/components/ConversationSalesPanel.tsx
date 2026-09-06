import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { describeError } from "../auth/AuthContext";
import { api, type SalesCaseContext, type SalesTurn } from "../api/client";
import {
  activeObjection,
  classifySalesError,
  latestSalesTurnForConversation,
  reasonCodeLabel,
  salesMoveLabel,
  salesStageLabel,
} from "../lib/salesCopy";

function Field({ label, children }: { label: string; children: string | null | undefined }) {
  return (
    <div>
      <div className="text-[11px] font-medium text-[#9C9488] mb-0.5">{label}</div>
      <div className="text-sm">{children?.trim() ? children : "Not captured yet"}</div>
    </div>
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
  const [loading, setLoading] = useState(Boolean(caseId));
  const [denied, setDenied] = useState(false);
  const [empty, setEmpty] = useState(!caseId);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setContext(null);
    setTurns([]);
    setDenied(false);
    setError(null);
    if (!caseId) {
      setEmpty(true);
      setLoading(false);
      return;
    }
    setEmpty(false);
    setLoading(true);
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
    return () => {
      cancelled = true;
    };
  }, [token, businessId, caseId]);

  const objection = context ? activeObjection(context.objections) : null;
  const latest = latestSalesTurnForConversation(turns, conversationId);

  return (
    <div className="rounded-xl border border-[#E7E5DE] bg-white p-4">
      <div className="text-xs font-semibold mb-1">Sales conversation</div>
      <p className="text-[11px] text-[#9C9488] mb-3 leading-relaxed">
        Sales stage is conversation progress. Case status on the right is the business commitment
        (qualification, booking, won) and is decided separately.
      </p>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-[#6B6459] py-2">
          <Loader2 size={14} className="animate-spin" /> Loading sales context…
        </div>
      )}

      {denied && (
        <div className="px-3 py-2 rounded-lg text-xs" style={{ backgroundColor: "#FBEBE9", color: "#8A3225" }}>
          You don’t have permission to view sales context for this case.
        </div>
      )}

      {error && (
        <div className="px-3 py-2 rounded-lg text-xs" style={{ backgroundColor: "#FBEBE9", color: "#8A3225" }}>
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
        <div className="flex flex-col gap-3">
          <Field label="Sales stage">{salesStageLabel(context.stage)}</Field>
          <Field label="Customer goal">{context.customer_goal}</Field>
          <Field label="Active objection">
            {objection
              ? `${objection.objection_type.replace(/_/g, " ").toLowerCase()} · ${objection.status.replace(/_/g, " ").toLowerCase()}${objection.cause ? ` · ${objection.cause}` : ""}`
              : null}
          </Field>
          {objection?.evidence_excerpt && (
            <p className="text-xs text-[#6B6459] -mt-2">“{objection.evidence_excerpt}”</p>
          )}
          <Field label="Last approved move">{context.last_move ? salesMoveLabel(context.last_move) : null}</Field>
          <div>
            <div className="text-[11px] font-medium text-[#9C9488] mb-0.5">Next approved action</div>
            <div className="text-sm font-medium">{salesMoveLabel(context.next_approved_action)}</div>
            <p className="text-xs text-[#6B6459] mt-0.5">{reasonCodeLabel(context.next_action_reason)}</p>
            <p className="text-[11px] text-[#9C9488] mt-1">
              Chosen by sales policy, not by the model. This does not change price, discount, or booking rules.
            </p>
          </div>
          {context.requires_human && (
            <div className="px-3 py-2 rounded-lg" style={{ backgroundColor: "#FFF8EE", color: "#8A561B" }}>
              <div className="text-[11px] font-semibold">Needs human review</div>
              <p className="text-xs mt-0.5">
                {context.human_review_reason
                  ? reasonCodeLabel(context.human_review_reason)
                  : "Policy handed this turn to you."}
              </p>
            </div>
          )}

          <div className="pt-3 border-t border-[#F0EFE9]">
            <div className="text-[11px] font-medium text-[#9C9488] mb-2">Provenance of the latest conversation turn</div>
            {!latest ? (
              <p className="text-xs text-[#9C9488]">No sales turns recorded for this conversation yet.</p>
            ) : (
              <div className="flex flex-col gap-2 text-xs text-[#6B6459]">
                <div>
                  <span className="font-medium text-[#151515]">Knowledge IDs: </span>
                  {latest.knowledge_ids.length > 0 ? latest.knowledge_ids.join(", ") : "None"}
                </div>
                <div>
                  <span className="font-medium text-[#151515]">Business facts: </span>
                  {latest.business_fact_ids.length > 0 ? latest.business_fact_ids.join(", ") : "None"}
                </div>
                <div>
                  <span className="font-medium text-[#151515]">Customer evidence: </span>
                  {latest.customer_evidence.length === 0
                    ? "None"
                    : latest.customer_evidence.map((item) => item.excerpt).join(" · ")}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
