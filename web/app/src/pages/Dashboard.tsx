import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search, Bell, ArrowUpRight, Clock, Phone, Mail, Loader2, ArrowDown, ArrowUp, MessageSquare } from "lucide-react";
import { Sidebar } from "../components/Sidebar";
import { useAuth, describeError } from "../auth/AuthContext";
import { api, type DashboardAnalytics, type DashboardCaseSummary } from "../api/client";
import { isoToUs, usToIso } from "../lib/usDate";
import {
  STATE_META,
  Stepper,
  StatePill,
  mapProcessState,
  describeEvent,
  formatRelativeTime,
  type CaseState,
} from "../components/Shared";

const FILTERS: (CaseState | "ALL")[] = ["ALL", "NEEDS_HUMAN", "QUALIFYING", "BOOKED", "LOST", "COMPLETED"];

type SortKey = "date" | "name";
type SortDirection = "asc" | "desc";

/**
 * A month/day/year field in English, always.
 *
 * This is deliberately NOT <input type="date">. Chrome renders that control
 * in the BROWSER's locale, not the document's: on a Russian-language Chrome
 * the reporting period read "дд.мм.гггг" even though the app is English and
 * US-only. Verified on the live page that lang="en-US" on the input does not
 * change it -- the format is not the page's to choose. So the field is ours.
 */
function UsDateField({ label, value, min, onChange }: {
  label: string;
  value: string;
  min?: string;
  onChange: (iso: string) => void;
}) {
  const [text, setText] = useState(() => isoToUs(value));
  const [invalid, setInvalid] = useState(false);

  useEffect(() => {
    setText(isoToUs(value));
    setInvalid(false);
  }, [value]);

  const commit = (raw: string) => {
    const trimmed = raw.trim();
    if (!trimmed) {
      setInvalid(false);
      onChange("");
      return;
    }
    const iso = usToIso(trimmed);
    if (!iso || (min && iso < min)) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    onChange(iso);
  };

  return (
    <label className="text-xs text-[#6B6459] flex flex-col gap-1">
      {label}
      <input
        type="text"
        inputMode="numeric"
        lang="en-US"
        autoComplete="off"
        placeholder="MM/DD/YYYY"
        aria-label={`${label} date, month slash day slash year`}
        aria-invalid={invalid}
        value={text}
        onChange={(event) => { setText(event.target.value); setInvalid(false); }}
        onBlur={(event) => commit(event.target.value)}
        onKeyDown={(event) => { if (event.key === "Enter") commit((event.target as HTMLInputElement).value); }}
        className="w-[118px] px-2.5 py-2 rounded-lg border text-sm text-[#151515] outline-none"
        style={{ borderColor: invalid ? "#B4483A" : "#E7E5DE" }}
      />
    </label>
  );
}

const ESCALATION_LABELS: Record<string, string> = {
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

const ESCALATION_ACTIONS: Record<string, string> = {
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

/**
 * Only where the outcome is NOT the ordinary one. Every card used to carry
 * "After a staff decision, the permitted workflow can continue from the
 * verified next step" as a second line -- the same sentence, word for word,
 * on five of six cards -- which buried the one line that differs and
 * actually tells you what to do.
 */
const ESCALATION_OUTCOMES: Record<string, string> = {
  already_pending: "No automatic next step will happen until a teammate resolves it.",
};

function nextStep(state: CaseState): string {
  if (state === "NEEDS_HUMAN") return "Review the conversation and reply";
  if (state === "QUALIFYING") return "Collect the remaining qualification details";
  if (state === "BOOKED") return "Prepare for the appointment";
  if (state === "LOST") return "Review whether reactivation is appropriate";
  if (state === "COMPLETED") return "Request a review or referral";
  return "Open the conversation to review the next action";
}

/**
 * `compact` is the metrics variant: smaller type, and the sub-line moves
 * BELOW the value instead of sitting beside it. Side by side, "7%" next to
 * "8/113 leads" was the pair that overflowed and clipped as soon as the tile
 * narrowed; stacked, it wraps instead of disappearing.
 *
 * A tile that is not a button gets no hover treatment, so "this opens the
 * list" and "this is just a number" stop looking identical.
 */
function StatCard({ label, value, sub, tone, onClick, emphasis = false, compact = false }: {
  label: string;
  value: string | number;
  sub?: string;
  tone?: string;
  onClick?: () => void;
  emphasis?: boolean;
  compact?: boolean;
}) {
  const content = <>
      <div className={`font-medium text-[#6B6459] ${compact ? "text-[11px] leading-tight mb-1" : "text-xs mb-1.5"}`}>{label}</div>
      <div className={compact ? "" : "flex items-baseline gap-2 flex-wrap"}>
        <span
          className={compact ? "text-[20px] leading-none block" : "text-[26px] leading-none"}
          style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}
        >
          {value}
        </span>
        {sub && (
          <span
            className={`font-medium ${compact ? "text-[11px] leading-tight block mt-1 break-words" : "text-xs"}`}
            style={{ color: tone || "#6B6459" }}
          >
            {sub}
          </span>
        )}
      </div>
    </>;
  const className = [
    "rounded-2xl border text-left min-w-0",
    compact ? "px-3 py-2.5" : "px-5 py-4",
    emphasis ? "border-[#C97A1F] bg-[#FFF9F2]" : "border-[#E7E5DE] bg-white",
    onClick ? "hover:border-[#B87333] transition-colors cursor-pointer" : "",
  ].join(" ");
  return onClick ? (
    <button type="button" onClick={onClick} className={className}>{content}</button>
  ) : <div className={className}>{content}</div>;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { token, businessId } = useAuth();
  const [cases, setCases] = useState<DashboardCaseSummary[] | null>(null);
  const [analytics, setAnalytics] = useState<DashboardAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<CaseState | "ALL">("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("date");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [confirmingReset, setConfirmingReset] = useState(false);
  const [resettingStats, setResettingStats] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);
  // Bumped after a statistics reset so the two fetches below re-run against
  // the new baseline without a page reload.
  const [statsVersion, setStatsVersion] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [includeTestData, setIncludeTestData] = useState(false);
  const [reasonFilter, setReasonFilter] = useState<string | null>(null);
  const [followUpOnly, setFollowUpOnly] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!token || !businessId) return;
    api
      .listCases(token, businessId, {
        startDate: startDate || undefined,
        endDate: endDate || undefined,
        includeTest: includeTestData,
      })
      .then((res) => {
        if (cancelled) return;
        setCases(res.cases);
        setSelectedId((prev) => prev ?? res.cases[0]?.case_id ?? null);
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err));
      });
    api
      .getDashboardAnalytics(token, businessId, {
        startDate: startDate || undefined,
        endDate: endDate || undefined,
        includeTest: includeTestData,
      })
      .then((result) => {
        if (!cancelled) setAnalytics(result);
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err));
      });
    return () => {
      cancelled = true;
    };
  }, [token, businessId, startDate, endDate, includeTestData, statsVersion]);

  const decorated = useMemo(
    () =>
      (cases ?? []).map((c) => {
        const { caseState, stage } = mapProcessState(c.current_state);
        const detail = c.latest_event_type ? describeEvent(c.latest_event_type).label : "No activity yet";
        const followUpDue = ["QUALIFYING", "FOLLOW_UP"].includes(c.current_state)
          && Date.now() - new Date(c.updated_at).getTime() > 24 * 60 * 60 * 1000;
        return { ...c, caseState, stage, detail, followUpDue };
      }),
    [cases],
  );

  const filtered = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    const visible = (filter === "ALL" ? [...decorated] : decorated.filter((c) => c.caseState === filter)).filter((c) => {
      if (followUpOnly && !c.followUpDue) return false;
      if (reasonFilter !== null && c.escalation_reason !== reasonFilter) return false;
      if (!query) return true;
      return [c.lead.name, c.lead.phone, c.lead.email, c.category, c.case_id, c.lead.lead_id]
        .some((value) => value?.toLowerCase().includes(query));
    });
    return visible.sort((left, right) => {
      if (sortBy === "date") {
        const comparison = new Date(left.created_at).getTime() - new Date(right.created_at).getTime();
        return sortDirection === "asc" ? comparison : -comparison;
      }
      const leftValue = left.lead.name;
      const rightValue = right.lead.name;
      if (!leftValue && !rightValue) return 0;
      if (!leftValue) return 1;
      if (!rightValue) return -1;
      const comparison = leftValue.localeCompare(rightValue, undefined, { sensitivity: "base" });
      return sortDirection === "asc" ? comparison : -comparison;
    });
  }, [decorated, filter, followUpOnly, reasonFilter, searchQuery, sortBy, sortDirection]);

  const changeSort = (nextSort: SortKey) => {
    setSortBy(nextSort);
    setSortDirection(nextSort === "date" ? "desc" : "asc");
  };


  const selected = useMemo(
    () => decorated.find((c) => c.case_id === selectedId) ?? decorated[0] ?? null,
    [decorated, selectedId],
  );

  const counts = useMemo(() => {
    const c = { needsHuman: 0, booked: 0, qualifying: 0, lost: 0, completed: 0, followUpDue: 0 };
    decorated.forEach((x) => {
      if (x.caseState === "NEEDS_HUMAN") c.needsHuman++;
      if (x.caseState === "BOOKED") c.booked++;
      if (x.caseState === "QUALIFYING") c.qualifying++;
      if (x.caseState === "LOST") c.lost++;
      if (x.caseState === "COMPLETED") c.completed++;
      if (x.followUpDue) c.followUpDue++;
    });
    return c;
  }, [decorated]);

  const sortDirectionLabel = sortBy === "date"
    ? sortDirection === "desc" ? "Newest first" : "Oldest first"
    : sortDirection === "asc" ? "A to Z" : "Z to A";

  /**
   * Starts the metrics from now. Lives here, next to the numbers it resets,
   * rather than only in Settings -> Reporting: the owner looking at a figure
   * they want cleared is looking at this screen.
   */
  const resetStatistics = async () => {
    if (!token || !businessId) return;
    setResettingStats(true);
    setResetError(null);
    try {
      await api.updateReportingSettings(token, businessId, { reset_statistics: true });
      setConfirmingReset(false);
      setStatsVersion((current) => current + 1);
    } catch (err) {
      setResetError(describeError(err));
    } finally {
      setResettingStats(false);
    }
  };

  const showAttention = (reason: string | null = null) => {
    setFilter("NEEDS_HUMAN");
    setFollowUpOnly(false);
    setReasonFilter(reason);
  };

  /**
   * The bell opens the conversations that need a person.
   *
   * It used to toggle a filter on the lead list 1173px further down the
   * page -- the click worked and absolutely nothing changed within sight, so
   * it read as a dead control. A notification badge has to take you to the
   * notifications.
   */
  const openAttentionQueue = () => {
    navigate("/app/conversations?attention=1");
  };

  const filterCount = (state: CaseState | "ALL") => {
    if (state === "ALL") return decorated.length;
    if (state === "NEEDS_HUMAN") return counts.needsHuman;
    if (state === "QUALIFYING") return counts.qualifying;
    if (state === "BOOKED") return counts.booked;
    if (state === "LOST") return counts.lost;
    return counts.completed;
  };

  useEffect(() => {
    setActionError(null);
  }, [selectedId]);

  // The case list (DashboardCaseSummary) has no conversation_id of its own --
  // look the conversation up by case_id first, then approve its pending
  // transition via the same StaffActionService.resolve the Conversations
  // page already uses (see Conversation.tsx's handleResolve). Patches the
  // resolved case in place from the response rather than a full re-fetch.
  const handleResolve = async () => {
    if (!token || !businessId || !selected) return;
    setResolvingId(selected.case_id);
    setActionError(null);
    try {
      const { conversations } = await api.listConversations(token, businessId);
      const match = conversations.find((c) => c.case_id === selected.case_id);
      if (!match) {
        setActionError("Couldn't find the conversation for this case.");
        return;
      }
      const result = await api.resolveConversation(token, businessId, match.conversation_id);
      if (result.case) {
        const resolvedCase = result.case;
        setCases((prev) => (prev ?? []).map((c) => (c.case_id === resolvedCase.case_id ? resolvedCase : c)));
      }
    } catch (err) {
      setActionError(describeError(err));
    } finally {
      setResolvingId(null);
    }
  };

  return (
    <div className="min-h-screen w-full flex" style={{ backgroundColor: "#F5F1EA", fontFamily: "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif", color: "#151515" }}>
      <Sidebar />
      <main className="flex-1 min-w-0 flex flex-col pt-14 md:pt-0">
        <header className="flex items-center justify-between px-6 md:px-8 py-4 border-b border-[#E7E5DE]">
          <div>
            <h1 className="text-xl" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}>Leads & cases</h1>
            <p className="text-sm text-[#6B6459] mt-0.5">Every conversation your engine has handled</p>
          </div>
          <div className="flex items-center gap-3">
            <div className="relative hidden sm:block">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9C9488]" />
              <input
                aria-label="Search leads"
                placeholder="Search leads..."
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                className="pl-9 pr-3 py-2 rounded-lg bg-white border border-[#E7E5DE] text-sm w-52 outline-none focus:ring-2 focus:ring-[#B8733333]"
              />
            </div>
            <button
              type="button"
              onClick={openAttentionQueue}
              aria-label={`Open the ${counts.needsHuman} conversations that need you`}
              title={`Open the ${counts.needsHuman} conversations that need you`}
              className="relative w-9 h-9 rounded-lg border border-[#E7E5DE] bg-white flex items-center justify-center transition-colors hover:border-[#B87333]"
            >
              <Bell size={16} strokeWidth={2} />
              {counts.needsHuman > 0 && (
                <span className="absolute -top-1 -right-1 min-w-4 h-4 px-1 rounded-full text-[10px] flex items-center justify-center text-white font-medium" style={{ backgroundColor: "#C97A1F" }}>{counts.needsHuman}</span>
              )}
            </button>
          </div>
        </header>

        <div className="p-6 md:p-8 flex flex-col gap-6">
          {error && (
            <div className="px-4 py-3 rounded-lg text-sm" style={{ backgroundColor: "#FBEBE9", color: "#8A3225" }}>
              Couldn't load your leads: {error}
            </div>
          )}

          {/* One band instead of three stacked sections plus a separate
              reporting card. Before this, Overview put 1173px of statistics
              above the lead list -- 1.68 screens of scrolling before the
              owner could touch a single lead, on nine tiles of which only
              four were clickable and nothing said which. Action is now on
              the left, numbers on the right, and the period + reset controls
              sit top-right where you look for them rather than three clicks
              deep in Settings. */}
          <div className="bg-white rounded-2xl border border-[#E7E5DE] p-4 md:p-5">
            <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3 mb-4">
              <div className="min-w-0">
                <h2 className="text-sm font-semibold">Today</h2>
                <p className="text-xs text-[#6B6459] mt-0.5">What needs you, and how the engine is doing.</p>
              </div>
              <div className="flex flex-wrap items-end gap-2">
                <UsDateField label="From" value={startDate} onChange={setStartDate} />
                <UsDateField label="To" value={endDate} min={startDate} onChange={setEndDate} />
                {(startDate || endDate) && (
                  <button
                    type="button"
                    onClick={() => { setStartDate(""); setEndDate(""); }}
                    className="text-xs font-medium px-3 py-2 rounded-lg border border-[#E7E5DE] hover:border-[#B87333] transition-colors"
                  >
                    All time
                  </button>
                )}
                {confirmingReset ? (
                  <span className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={resetStatistics}
                      disabled={resettingStats}
                      className="text-xs font-medium px-3 py-2 rounded-lg border border-[#C97A1F] text-[#8A561B] bg-[#FFF9F2] disabled:opacity-50"
                    >
                      {resettingStats ? "Resetting…" : "Confirm reset"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmingReset(false)}
                      className="text-xs font-medium px-3 py-2 rounded-lg border border-[#E7E5DE]"
                    >
                      Cancel
                    </button>
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={() => setConfirmingReset(true)}
                    title="Start the metrics from now. Conversations, cases and audit history are never deleted."
                    className="text-xs font-medium px-3 py-2 rounded-lg border border-[#E7E5DE] hover:border-[#B87333] transition-colors"
                  >
                    Reset statistics
                  </button>
                )}
              </div>
            </div>

            {/* min-[880px] rather than lg (1024). The breakpoint is measured
                against the WINDOW, but this band lives inside main, which the
                313px sidebar has already narrowed -- on a real 901px window
                the split never engaged and everything stacked. 880 is where
                260 + a two-up metrics grid still has room to breathe. */}
            <div className="grid gap-3 min-[880px]:grid-cols-[minmax(0,240px)_minmax(0,1fr)]">
              <div className="grid gap-3 sm:grid-cols-2 min-[880px]:grid-cols-1 min-[880px]:content-start">
                <StatCard
                  label="Needs your attention"
                  value={counts.needsHuman}
                  sub="review queue"
                  tone="#C97A1F"
                  onClick={() => showAttention()}
                  emphasis
                />
                <StatCard
                  label="Follow-up due"
                  value={counts.followUpDue}
                  sub="waiting 24h+"
                  tone="#C97A1F"
                  onClick={() => { setFilter("ALL"); setReasonFilter(null); setFollowUpOnly(true); }}
                />
              </div>

              {/* Pairs must stay pairs. Row-major across three columns split
                    "Booking rate" and "Lost rate" -- the two outcome rates --
                    onto different rows and left Lost rate opening row two on
                    the far left, reading as if it belonged to the action
                    column. grid-flow-col with two fixed rows fills column by
                    column instead, so each column is one pair: volume,
                    outcome rates, engine health. Below 1024 the plain
                    two-column row-major order gives the same pairs. */}
              <div className="grid gap-2 grid-cols-2 min-[1024px]:grid-cols-3 min-[1024px]:grid-rows-2 min-[1024px]:grid-flow-col">
                <StatCard compact label="Qualifying now" value={counts.qualifying} sub="active leads" tone="#B87333" onClick={() => { setFilter("QUALIFYING"); setReasonFilter(null); setFollowUpOnly(false); }} />
                <StatCard compact label="Booked" value={counts.booked} sub="active cases" tone="#1E7B52" onClick={() => { setFilter("BOOKED"); setReasonFilter(null); setFollowUpOnly(false); }} />
                {/* Deliberately not clickable, unlike "Booked" above: this
                    counts cases that EVER booked, while the list filters on
                    the state a case is in NOW. Linking it opened a list that
                    disagreed with the number printed on it. */}
                <StatCard compact label="Booking rate" value={analytics ? `${Math.round(analytics.booking_conversion_rate * 100)}%` : "—"} sub={analytics ? `${analytics.booked_cases}/${analytics.total_cases} leads` : undefined} tone="#1E7B52" />
                <StatCard compact label="Lost rate" value={analytics ? `${Math.round(analytics.lost_rate * 100)}%` : "—"} sub={analytics ? `${analytics.lost_cases}/${analytics.total_cases} leads` : undefined} onClick={() => { setFilter("LOST"); setReasonFilter(null); setFollowUpOnly(false); }} />
                <StatCard compact label="Escalation rate" value={analytics ? `${Math.round(analytics.escalation_rate * 100)}%` : "—"} sub={analytics ? `${analytics.escalated_cases}/${analytics.total_cases} leads` : undefined} tone="#C97A1F" />
                <StatCard compact label="Median first response" value={analytics?.median_first_response_seconds != null ? `${Math.round(analytics.median_first_response_seconds)}s` : "—"} sub={analytics ? `${analytics.response_samples} samples` : undefined} tone="#1E7B52" />
              </div>
            </div>

            {(resetError || (analytics && analytics.hidden_test_cases > 0) || (analytics?.stats_since && !startDate && !endDate)) && (
              <div className="mt-3 pt-3 border-t border-[#E7E5DE] flex flex-wrap items-center gap-x-4 gap-y-2">
                {resetError && <span className="text-xs text-[#8A3225]">{resetError}</span>}
                {analytics && analytics.hidden_test_cases > 0 && (
                  <label className="text-xs text-[#6B6459] flex items-center gap-2">
                    <input type="checkbox" checked={includeTestData} onChange={(event) => setIncludeTestData(event.target.checked)} className="accent-[#B87333]" />
                    {includeTestData
                      ? "Including test data"
                      : `Test data hidden · ${analytics.hidden_test_conversations} conversations / ${analytics.hidden_test_cases} cases`}
                  </label>
                )}
                {analytics?.stats_since && !startDate && !endDate && (
                  <span className="text-xs text-[#6B6459]">Metrics count from your statistics baseline.</span>
                )}
              </div>
            )}
          </div>


          {cases === null && !error ? (
            <div className="flex items-center gap-2 text-sm text-[#6B6459] py-12 justify-center">
              <Loader2 size={16} className="animate-spin" /> Loading your leads…
            </div>
          ) : decorated.length === 0 ? (
            <div className="bg-white rounded-2xl border border-[#E7E5DE] px-6 py-12 text-center">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center mx-auto mb-4 text-white" style={{ backgroundColor: "#B87333" }}>
                <MessageSquare size={18} />
              </div>
              <h2 className="text-base font-semibold mb-1.5">No conversations yet</h2>
              <p className="text-sm text-[#6B6459] max-w-md mx-auto mb-6">
                Flywheel is on. Put the chat snippet on your site (or open the preview) so the next person who writes in shows up here.
              </p>
              <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
                <button
                  type="button"
                  onClick={() => navigate("/app/settings?tab=widget")}
                  className="text-sm font-medium text-white px-4 py-2.5 rounded-lg"
                  style={{ backgroundColor: "#151515" }}
                >
                  Install website chat
                </button>
                <button
                  type="button"
                  onClick={() => navigate("/app/conversations")}
                  className="text-sm font-medium px-4 py-2.5 rounded-lg border border-[#E7E5DE]"
                >
                  Open conversations
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col lg:flex-row gap-6">
              <div className="flex-1 min-w-0 bg-white rounded-2xl border border-[#E7E5DE] overflow-hidden">
                {/* flex-wrap, not overflow-x-auto. The chips used to sit on
                    one scrolling line with the sort control pinned beside
                    them, so at 1440px "Completed" was cut in half and at
                    laptop widths "Booked" was too -- a filter you cannot see
                    is a filter that does not exist. They now wrap onto as
                    many rows as they need and every chip stays whole. The
                    sort control is gone: the list orders itself by urgency
                    (see `filtered`), which is the only order a work queue
                    wants. */}
                <div className="flex flex-wrap items-center gap-2 px-5 py-3 border-b border-[#E7E5DE]">
                  {FILTERS.map((s) => (
                    <button
                      key={s}
                      onClick={() => { setFilter(s); setReasonFilter(null); setFollowUpOnly(false); }}
                      className="px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors"
                      style={{ backgroundColor: filter === s ? "#151515" : "transparent", color: filter === s ? "#fff" : "#6B6459" }}
                    >
                      {s === "ALL" ? `All (${filterCount(s)})` : `${STATE_META[s].label} (${filterCount(s)})`}
                    </button>
                  ))}
                  <div className="ml-auto flex items-center gap-1.5 shrink-0 text-xs text-[#6B6459]">
                    <label>
                    <span className="sr-only">Sort leads</span>
                    <select
                      aria-label="Sort leads"
                      value={sortBy}
                      onChange={(event) => changeSort(event.target.value as SortKey)}
                      className="bg-white border border-[#E7E5DE] rounded-lg px-2.5 py-1.5 outline-none"
                    >
                      <option value="date">Date added</option>
                      <option value="name">Name</option>
                    </select>
                    </label>
                    <button
                      type="button"
                      onClick={() => setSortDirection((current) => current === "asc" ? "desc" : "asc")}
                      aria-label={`Sort direction: ${sortDirectionLabel}. Click to reverse.`}
                      title={`${sortDirectionLabel} — click to reverse`}
                      className="w-8 h-8 rounded-lg bg-white border border-[#E7E5DE] flex items-center justify-center hover:border-[#B87333] transition-colors"
                    >
                      {sortDirection === "asc" ? <ArrowUp size={14} /> : <ArrowDown size={14} />}
                    </button>
                    <span className="hidden xl:inline min-w-[68px]">{sortDirectionLabel}</span>
                  </div>
                </div>
                {/* What the "Review queue" card used to be, in one line.
                    That card was a third copy of this list's own filters: it
                    repeated the 77, repeated "view all", and its six reason
                    cards did what these chips do -- while taking most of a
                    screen and pushing the leads below the fold. The per-lead
                    guidance it carried now sits on the selected lead, where
                    you act on it. */}
                {filter === "NEEDS_HUMAN" && analytics && Object.keys(analytics.escalation_reasons).length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 px-5 py-2 border-b border-[#E7E5DE] bg-[#FDFCF9]">
                    <span className="text-[11px] text-[#9C9488] mr-1">Why:</span>
                    {Object.entries(analytics.escalation_reasons)
                      .sort(([, left], [, right]) => right - left)
                      .map(([reason, count]) => (
                        <button
                          key={reason}
                          type="button"
                          onClick={() => setReasonFilter(reasonFilter === reason ? null : reason)}
                          className="px-2.5 py-1 rounded-full text-[11px] font-medium border transition-colors"
                          style={{
                            backgroundColor: reasonFilter === reason ? "#F5E7D6" : "#fff",
                            borderColor: reasonFilter === reason ? "#B87333" : "#E7E5DE",
                          }}
                        >
                          {ESCALATION_LABELS[reason] ?? "Human review"} {count}
                        </button>
                      ))}
                  </div>
                )}
                {(filter !== "ALL" || reasonFilter !== null || followUpOnly) && (
                  <div className="px-5 py-2 text-xs text-[#6B6459] bg-[#FFF9F2] border-b border-[#E7E5DE] flex items-center justify-between gap-3">
                    <span>Showing {filtered.length} {reasonFilter ? `leads: ${ESCALATION_LABELS[reasonFilter] ?? "human review"}` : followUpOnly ? "follow-ups due" : "filtered leads"}.</span>
                    <button type="button" onClick={() => { setFilter("ALL"); setReasonFilter(null); setFollowUpOnly(false); }} className="font-medium text-[#151515] underline">Clear filter</button>
                  </div>
                )}
                <ul>
                  {filtered.length === 0 && (
                    <li className="px-5 py-10 text-center text-sm text-[#6B6459]">No leads match your search and filters.</li>
                  )}
                  {filtered.map((c) => (
                    <li
                      key={c.case_id}
                      onClick={() => navigate(`/app/conversations?case=${c.case_id}`)}
                      className="px-5 py-4 border-b border-[#F0EFE9] last:border-0 cursor-pointer transition-colors"
                      style={{ backgroundColor: selected?.case_id === c.case_id ? "#FAFAF7" : "transparent" }}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-sm font-semibold truncate">{c.lead.name || "Unnamed lead"}</span>
                            <span className="text-[11px] text-[#9C9488]" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>{c.case_id.slice(0, 8)}</span>
                          </div>
                          <div className="text-sm text-[#6B6459] truncate">{c.category ?? "Uncategorized"} · {c.detail}</div>
                          {c.followUpDue && <div className="mt-1 text-[11px] font-medium text-[#C97A1F]">Follow-up overdue</div>}
                        </div>
                        <div className="flex flex-col items-end gap-2 shrink-0">
                          <StatePill state={c.caseState} />
                          <span className="text-[11px] text-[#9C9488] flex items-center gap-1"><Clock size={11} /> {formatRelativeTime(c.updated_at)}</span>
                        </div>
                      </div>
                      <div className="mt-3"><Stepper stage={c.stage} color={STATE_META[c.caseState].color} /></div>
                    </li>
                  ))}
                </ul>
              </div>

              {selected && (
                <div className="w-full lg:w-80 shrink-0 bg-white rounded-2xl border border-[#E7E5DE] p-5 h-fit sticky top-6">
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-[11px] uppercase tracking-wide text-[#9C9488] font-medium" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>{selected.case_id.slice(0, 8)}</span>
                    <StatePill state={selected.caseState} />
                  </div>
                  <h2 className="text-lg font-semibold mb-1">{selected.lead.name || "Unnamed lead"}</h2>
                  <p className="text-sm text-[#6B6459] mb-4">{selected.event_count} event{selected.event_count === 1 ? "" : "s"} recorded</p>
                  <div className="mb-5">
                    <div className="text-xs font-medium text-[#9C9488] mb-2">Where this case is</div>
                    <Stepper stage={selected.stage} color={STATE_META[selected.caseState].color} labels />
                  </div>
                  <div className="rounded-xl p-3 mb-5" style={{ backgroundColor: "#FAFAF7" }}>
                    <p className="text-sm leading-relaxed">{selected.detail}</p>
                  </div>
                  {selected.escalation_reason && (
                    <div className="rounded-xl border border-[#E8CFAF] bg-[#FFF8EE] p-3 mb-4">
                      <div className="text-xs font-medium text-[#8A561B] mb-1">Why it needs attention</div>
                      <p className="text-sm text-[#6B6459]">
                        {ESCALATION_LABELS[selected.escalation_reason] ?? "Human review requested"}
                      </p>
                      <p className="text-sm text-[#6B6459] mt-1.5">
                        Next safe action: {ESCALATION_ACTIONS[selected.escalation_reason] ?? "Open the lead and choose the next safe step."}
                      </p>
                      {ESCALATION_OUTCOMES[selected.escalation_reason] && (
                        <p className="text-xs text-[#6B6459] mt-1.5">{ESCALATION_OUTCOMES[selected.escalation_reason]}</p>
                      )}
                    </div>
                  )}
                  <div className="mb-5">
                    <div className="text-xs font-medium text-[#9C9488] mb-1">Recommended next step</div>
                    <p className="text-sm">{nextStep(selected.caseState)}</p>
                  </div>
                  {actionError && (
                    <div className="mb-3 px-3 py-2 rounded-lg text-xs" style={{ backgroundColor: "#FBEBE9", color: "#8A3225" }}>
                      {actionError}
                    </div>
                  )}
                  <div className="flex flex-col gap-2">
                    <button onClick={() => navigate(`/app/conversations?case=${selected.case_id}`)} className="w-full py-2.5 rounded-lg text-sm font-medium text-white flex items-center justify-center gap-2" style={{ backgroundColor: "#151515" }}>
                      Open conversation <ArrowUpRight size={14} />
                    </button>
                    {selected.caseState === "NEEDS_HUMAN" && (
                      <button
                        onClick={handleResolve}
                        disabled={resolvingId === selected.case_id}
                        className="w-full py-2.5 rounded-lg text-sm font-medium border border-[#E7E5DE] flex items-center justify-center gap-1.5 disabled:opacity-50"
                      >
                        {resolvingId === selected.case_id && <Loader2 size={14} className="animate-spin" />}
                        Mark resolved
                      </button>
                    )}
                  </div>
                  <div className="mt-5 pt-4 border-t border-[#F0EFE9] flex items-center gap-4 text-xs text-[#6B6459]">
                    <span className="flex items-center gap-1.5"><Phone size={12} /> {selected.lead.phone || "Not on file"}</span>
                    <span className="flex items-center gap-1.5"><Mail size={12} /> {selected.lead.email || "Not on file"}</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
