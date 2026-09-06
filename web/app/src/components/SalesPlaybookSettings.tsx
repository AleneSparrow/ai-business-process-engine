import { useEffect, useMemo, useState } from "react";
import { BookOpen, Check, Loader2, X } from "lucide-react";
import { describeError } from "../auth/AuthContext";
import {
  ApiError,
  api,
  type SalesKnowledgeCard,
  type SalesKnowledgeStatus,
  type SalesPlaybook,
} from "../api/client";
import { formatRelativeTime } from "./Shared";
import {
  KNOWLEDGE_STATUS_LABELS,
  PLAYBOOK_STATUS_LABELS,
  beginKnowledgeReview,
  canConfirmKnowledgeReview,
  canReviewKnowledgeCard,
  classifySalesError,
  isPendingReviewForCard,
  knowledgeCardDetailFields,
  knowledgeReviewConfirmation,
  knowledgeSourceLabel,
  type PendingKnowledgeReview,
} from "../lib/salesCopy";

const FILTERS: { key: "ALL" | SalesKnowledgeStatus; label: string }[] = [
  { key: "ALL", label: "All" },
  { key: "CANDIDATE", label: "Candidates" },
  { key: "APPROVED", label: "Approved" },
  { key: "REJECTED", label: "Rejected" },
];

function statusTone(status: SalesKnowledgeStatus): { color: string; backgroundColor: string } {
  if (status === "APPROVED") return { color: "#1E7B52", backgroundColor: "#E9F5EF" };
  if (status === "REJECTED") return { color: "#8A3225", backgroundColor: "#FBEBE9" };
  return { color: "#C73618", backgroundColor: "#FFE8E1" };
}

function playbookTone(status: SalesPlaybook["status"]): { color: string; backgroundColor: string } {
  if (status === "PUBLISHED") return { color: "#1E7B52", backgroundColor: "#E9F5EF" };
  if (status === "ARCHIVED") return { color: "#6B6459", backgroundColor: "#F1F1EF" };
  return { color: "#C73618", backgroundColor: "#FFE8E1" };
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
  const [filter, setFilter] = useState<"ALL" | SalesKnowledgeStatus>("ALL");
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [openDetails, setOpenDetails] = useState<Record<string, boolean>>({});
  const [pendingReview, setPendingReview] = useState<PendingKnowledgeReview | null>(null);

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

  const visibleCards = useMemo(() => {
    if (!cards) return [];
    return filter === "ALL" ? cards : cards.filter((card) => card.status === filter);
  }, [cards, filter]);

  const cardKey = (card: SalesKnowledgeCard) => `${card.knowledge_id}:${card.version}`;

  const toggleDetails = (card: SalesKnowledgeCard) => {
    const key = cardKey(card);
    const nextOpen = !openDetails[key];
    setOpenDetails((current) => ({ ...current, [key]: nextOpen }));
    if (!nextOpen && isPendingReviewForCard(pendingReview, card)) {
      setPendingReview(null);
    }
  };

  const startReview = (card: SalesKnowledgeCard, action: "approve" | "reject") => {
    const pending = beginKnowledgeReview(card, Boolean(openDetails[cardKey(card)]), action);
    if (!pending) return;
    setReviewError(null);
    setPendingReview(pending);
  };

  const review = async () => {
    if (!pendingReview || reviewing) return;
    setReviewing(true);
    setReviewError(null);
    try {
      const updated =
        pendingReview.action === "approve"
          ? await api.approveSalesKnowledgeCard(
              token, businessId, pendingReview.knowledgeId, pendingReview.version,
            )
          : await api.rejectSalesKnowledgeCard(
              token, businessId, pendingReview.knowledgeId, pendingReview.version,
            );
      setCards((current) =>
        (current ?? []).map((item) =>
          item.knowledge_id === updated.knowledge_id && item.version === updated.version ? updated : item,
        ),
      );
      setPendingReview(null);
    } catch (err) {
      if (err instanceof ApiError && err.code === "sales_knowledge_already_reviewed") {
        setReviewError(describeError(err));
        setPendingReview(null);
        const refreshed = await api.listSalesKnowledgeCards(token, businessId).catch(() => null);
        if (refreshed) setCards(refreshed.cards);
      } else if (classifySalesError(err) === "denied") {
        setDenied(true);
        setPendingReview(null);
      } else {
        setReviewError(describeError(err));
      }
    } finally {
      setReviewing(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-mute py-8">
        <Loader2 size={16} className="animate-spin" /> Loading sales playbook…
      </div>
    );
  }

  if (denied) {
    return (
      <div className="px-4 py-3 rounded-lg text-sm" style={{ backgroundColor: "#FBEBE9", color: "#8A3225" }}>
        You don’t have permission to view the sales playbook for this business.
      </div>
    );
  }

  if (error) {
    return (
      <div className="px-4 py-3 rounded-lg text-sm" style={{ backgroundColor: "#FBEBE9", color: "#8A3225" }}>
        {error}
      </div>
    );
  }

  return (
    <div>
      <p className="text-sm text-mute mb-6 leading-relaxed">
        The sales playbook is the approved conversation method. It is separate from case status
        (qualification, booking, won). AI may phrase an approved move; it does not set prices,
        discounts, or bookings.
      </p>

      {playbook ? (
        <div className="rounded-2xl border p-5 mb-6" style={{ borderColor: "#E4DCCB" }}>
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div className="flex items-start gap-3">
              <span className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0 text-white" style={{ backgroundColor: "#FF5A36" }}>
                <BookOpen size={18} />
              </span>
              <div>
                <h2 className="text-base font-semibold">Active playbook</h2>
                <p className="text-sm text-mute mt-0.5" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>
                  Version {playbook.version}
                  {playbook.published_at ? ` · published ${formatRelativeTime(playbook.published_at)}` : ""}
                </p>
              </div>
            </div>
            <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium" style={playbookTone(playbook.status)}>
              {PLAYBOOK_STATUS_LABELS[playbook.status]}
            </span>
          </div>
          <p className="text-xs text-clay mt-4">
            Read-only. A published playbook cannot be edited here. New methods are published as a new version.
          </p>
        </div>
      ) : (
        <div className="rounded-2xl border p-5 mb-6" style={{ borderColor: "#E4DCCB", backgroundColor: "#FAFAF7" }}>
          <h2 className="text-base font-semibold">No published playbook</h2>
          <p className="text-sm text-mute mt-1 leading-relaxed">
            There is no live sales playbook for this business yet. Draft or archived versions, if any, are listed below. The engine will not use a draft as the live method.
          </p>
        </div>
      )}

      {versions.length > 0 && (
        <div className="mb-8">
          <div className="text-sm font-semibold mb-3">Playbook versions</div>
          <div className="flex flex-col gap-2">
            {versions.map((item) => (
              <div key={item.version} className="flex items-center justify-between gap-3 px-3 py-2.5 rounded-xl border border-line text-sm">
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
      <p className="text-sm text-mute mb-4 leading-relaxed">
        Only approved cards may be used in a customer reply. Candidates stay unused until you approve or reject them.
      </p>

      <div className="flex flex-wrap gap-1.5 mb-4">
        {FILTERS.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setFilter(item.key)}
            className="px-3 py-1.5 rounded-lg text-xs font-medium border"
            style={{
              borderColor: filter === item.key ? "#0B0B0D" : "#E4DCCB",
              backgroundColor: filter === item.key ? "#0B0B0D" : "#fff",
              color: filter === item.key ? "#fff" : "#6B6459",
            }}
          >
            {item.label}
          </button>
        ))}
      </div>

      {reviewError && (
        <div className="mb-4 px-4 py-3 rounded-lg text-sm" style={{ backgroundColor: "#FBEBE9", color: "#8A3225" }}>
          {reviewError}
        </div>
      )}

      {visibleCards.length === 0 ? (
        <p className="text-sm text-clay py-4">
          {cards && cards.length > 0 ? "No cards match this filter." : "No knowledge cards yet."}
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {visibleCards.map((card) => {
            const source = knowledgeSourceLabel(card.source);
            const key = cardKey(card);
            const detailsOpen = Boolean(openDetails[key]);
            const details = knowledgeCardDetailFields(card);
            const pendingHere = isPendingReviewForCard(pendingReview, card) ? pendingReview : null;
            const confirmation = pendingHere ? knowledgeReviewConfirmation(pendingHere) : null;
            const showReviewActions = canConfirmKnowledgeReview(card.status, detailsOpen) && !pendingHere;
            return (
              <div key={key} className="p-4 rounded-xl border border-line">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="min-w-0">
                    <div className="text-sm font-medium">{card.principle}</div>
                    <p className="text-xs text-mute mt-1">
                      <span style={{ fontFamily: "'IBM Plex Mono', monospace" }}>{card.knowledge_id}</span>
                      {source.title ? ` · ${source.title}` : ""}
                      {source.location ? ` · ${source.location}` : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-[11px] text-clay" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>
                      v{card.version}
                    </span>
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium" style={statusTone(card.status)}>
                      {KNOWLEDGE_STATUS_LABELS[card.status]}
                    </span>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => toggleDetails(card)}
                  className="mt-3 text-xs font-medium text-coral"
                >
                  {detailsOpen ? "Hide details" : "View details"}
                </button>

                {detailsOpen && (
                  <dl className="mt-4 flex flex-col gap-3">
                    {details.map((field) => (
                      <div key={field.label}>
                        <dt className="text-[11px] font-medium text-clay">{field.label}</dt>
                        <dd className="text-sm mt-0.5">
                          {field.values.length === 1 ? (
                            field.values[0]
                          ) : (
                            <ul className="list-disc pl-4 flex flex-col gap-1">
                              {field.values.map((value, index) => (
                                <li key={`${field.label}-${index}`}>{value}</li>
                              ))}
                            </ul>
                          )}
                        </dd>
                      </div>
                    ))}
                  </dl>
                )}

                {showReviewActions && (
                  <div className="flex items-center gap-2 mt-4">
                    <button
                      type="button"
                      disabled={reviewing}
                      onClick={() => startReview(card, "approve")}
                      className="text-xs font-medium text-white px-3 py-2 rounded-lg flex items-center gap-1.5 disabled:opacity-50"
                      style={{ backgroundColor: "#0B0B0D" }}
                    >
                      <Check size={12} />
                      Approve
                    </button>
                    <button
                      type="button"
                      disabled={reviewing}
                      onClick={() => startReview(card, "reject")}
                      className="text-xs font-medium px-3 py-2 rounded-lg border border-line flex items-center gap-1.5 disabled:opacity-50"
                    >
                      <X size={12} />
                      Reject
                    </button>
                  </div>
                )}

                {confirmation && (
                  <div className="mt-4 p-3 rounded-lg border" style={{ borderColor: "#E8CFAF", backgroundColor: "#FFE8E1" }}>
                    <p className="text-sm">
                      Confirm {confirmation.actionLabel} of knowledge card{" "}
                      <span style={{ fontFamily: "'IBM Plex Mono', monospace" }}>{confirmation.knowledgeId}</span>
                      {" "}version {confirmation.version}.
                    </p>
                    <p className="text-xs text-[#C73618] mt-1.5">{confirmation.warning}</p>
                    <div className="flex flex-wrap items-center gap-2 mt-3">
                      <button
                        type="button"
                        disabled={reviewing}
                        onClick={review}
                        className="text-xs font-medium text-white px-3 py-2 rounded-lg flex items-center gap-1.5 disabled:opacity-50"
                        style={{ backgroundColor: "#0B0B0D" }}
                      >
                        {reviewing && <Loader2 size={12} className="animate-spin" />}
                        {confirmation.action === "approve" ? "Confirm approval" : "Confirm rejection"}
                      </button>
                      <button
                        type="button"
                        disabled={reviewing}
                        onClick={() => setPendingReview(null)}
                        className="text-xs font-medium px-3 py-2 rounded-lg border border-line disabled:opacity-50"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}

                {!canReviewKnowledgeCard(card.status) && card.reviewed_at && (
                  <p className="text-[11px] text-clay mt-3">
                    Reviewed {formatRelativeTime(card.reviewed_at)}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
