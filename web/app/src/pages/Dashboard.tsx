import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search, Bell, ArrowUpRight, Clock, Phone, Mail, Loader2, ArrowDown, ArrowUp } from "lucide-react";
import { Sidebar } from "../components/Sidebar";
import { useAuth, describeError } from "../auth/AuthContext";
import { api, type DashboardAnalytics, type DashboardCaseSummary } from "../api/client";
import {
  STAGES,
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

function nextStep(state: CaseState): string {
  if (state === "NEEDS_HUMAN") return "Review the conversation and reply";
  if (state === "QUALIFYING") return "Collect the remaining qualification details";
  if (state === "BOOKED") return "Prepare for the appointment";
  if (state === "LOST") return "Review whether reactivation is appropriate";
  if (state === "COMPLETED") return "Request a review or referral";
  return "Open the conversation to review the next action";
}

function StatCard({ label, value, sub, tone }: { label: string; value: string | number; sub?: string; tone?: string }) {
  return (
    <div className="bg-white rounded-2xl border border-[#E7E5DE] px-5 py-4 flex-1 min-w-[150px]">
      <div className="text-xs font-medium text-[#6B6459] mb-1.5">{label}</div>
      <div className="flex items-baseline gap-2">
        <span className="text-[26px] leading-none" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}>{value}</span>
        {sub && <span className="text-xs font-medium" style={{ color: tone || "#6B6459" }}>{sub}</span>}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { token, businessId } = useAuth();
  const [cases, setCases] = useState<DashboardCaseSummary[] | null>(null);
  const [analytics, setAnalytics] = useState<DashboardAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<CaseState | "ALL">("ALL");
  const [sortBy, setSortBy] = useState<SortKey>("date");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!token || !businessId) return;
    api
      .listCases(token, businessId)
      .then((res) => {
        if (cancelled) return;
        setCases(res.cases);
        setSelectedId((prev) => prev ?? res.cases[0]?.case_id ?? null);
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err));
      });
    api
      .getDashboardAnalytics(token, businessId)
      .then((result) => {
        if (!cancelled) setAnalytics(result);
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err));
      });
    return () => {
      cancelled = true;
    };
  }, [token, businessId]);

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
    const query = searchQuery.trim().toLocaleLowerCase();
    const visible = (filter === "ALL" ? [...decorated] : decorated.filter((c) => c.caseState === filter)).filter((c) => {
      if (!query) return true;
      return [c.lead.name, c.lead.phone, c.lead.email, c.category, c.case_id, c.lead.lead_id]
        .some((value) => value?.toLocaleLowerCase().includes(query));
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
  }, [decorated, filter, searchQuery, sortBy, sortDirection]);

  const changeSort = (nextSort: SortKey) => {
    setSortBy(nextSort);
    setSortDirection(nextSort === "date" ? "desc" : "asc");
  };

  const sortDirectionLabel = sortBy === "date"
    ? sortDirection === "desc" ? "Newest first" : "Oldest first"
    : sortDirection === "asc" ? "A to Z" : "Z to A";

  const selected = useMemo(
    () => decorated.find((c) => c.case_id === selectedId) ?? decorated[0] ?? null,
    [decorated, selectedId],
  );

  const counts = useMemo(() => {
    const c = { needsHuman: 0, booked: 0, qualifying: 0, followUpDue: 0 };
    decorated.forEach((x) => {
      if (x.caseState === "NEEDS_HUMAN") c.needsHuman++;
      if (x.caseState === "BOOKED") c.booked++;
      if (x.caseState === "QUALIFYING") c.qualifying++;
      if (x.followUpDue) c.followUpDue++;
    });
    return c;
  }, [decorated]);

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
              onClick={() => setFilter("NEEDS_HUMAN")}
              aria-label="Show leads that need attention"
              className="relative w-9 h-9 rounded-lg bg-white border border-[#E7E5DE] flex items-center justify-center"
            >
              <Bell size={16} strokeWidth={2} />
              <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full text-[10px] flex items-center justify-center text-white font-medium" style={{ backgroundColor: "#C97A1F" }}>{counts.needsHuman}</span>
            </button>
          </div>
        </header>

        <div className="p-6 md:p-8 flex flex-col gap-6">
          {error && (
            <div className="px-4 py-3 rounded-lg text-sm" style={{ backgroundColor: "#FBEBE9", color: "#8A3225" }}>
              Couldn't load your leads: {error}
            </div>
          )}

          <div className="flex flex-wrap gap-3">
            <StatCard label="Needs your attention" value={counts.needsHuman} tone="#C97A1F" />
            <StatCard label="Qualifying now" value={counts.qualifying} tone="#B87333" />
            <StatCard label="Booked" value={counts.booked} tone="#1E7B52" />
            <StatCard label="Follow-up due" value={counts.followUpDue} tone="#C97A1F" />
            <StatCard
              label="Booking rate"
              value={analytics ? `${Math.round(analytics.booking_conversion_rate * 100)}%` : "—"}
              sub={analytics ? `${analytics.booked_cases}/${analytics.total_cases}` : undefined}
              tone="#1E7B52"
            />
            <StatCard
              label="Escalation rate"
              value={analytics ? `${Math.round(analytics.escalation_rate * 100)}%` : "—"}
              sub={analytics ? `${analytics.escalated_cases}/${analytics.total_cases}` : undefined}
              tone="#C97A1F"
            />
            <StatCard
              label="Lost rate"
              value={analytics ? `${Math.round(analytics.lost_rate * 100)}%` : "—"}
              sub={analytics ? `${analytics.lost_cases}/${analytics.total_cases}` : undefined}
            />
            <StatCard
              label="Median first response"
              value={analytics?.median_first_response_seconds != null ? `${Math.round(analytics.median_first_response_seconds)}s` : "—"}
              sub={analytics ? `${analytics.response_samples} samples` : undefined}
              tone="#1E7B52"
            />
          </div>

          {cases === null && !error ? (
            <div className="flex items-center gap-2 text-sm text-[#6B6459] py-12 justify-center">
              <Loader2 size={16} className="animate-spin" /> Loading your leads…
            </div>
          ) : decorated.length === 0 ? (
            <div className="bg-white rounded-2xl border border-[#E7E5DE] px-6 py-12 text-center text-sm text-[#6B6459]">
              No leads yet. Once a customer messages your widget or number, cases will show up here in real time.
            </div>
          ) : (
            <div className="flex flex-col lg:flex-row gap-6">
              <div className="flex-1 min-w-0 bg-white rounded-2xl border border-[#E7E5DE] overflow-hidden">
                <div className="flex items-center justify-between gap-3 px-5 py-3 border-b border-[#E7E5DE]">
                  <div className="flex items-center gap-2 overflow-x-auto">
                    {FILTERS.map((s) => (
                      <button
                        key={s}
                        onClick={() => setFilter(s)}
                        className="px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors"
                        style={{ backgroundColor: filter === s ? "#151515" : "transparent", color: filter === s ? "#fff" : "#6B6459" }}
                      >
                        {s === "ALL" ? "All" : STATE_META[s].label}
                      </button>
                    ))}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0 text-xs text-[#6B6459]">
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
                    <Stepper stage={selected.stage} color={STATE_META[selected.caseState].color} />
                    <div className="flex justify-between mt-1.5">
                      {STAGES.map((s) => <span key={s} className="text-[10px] text-[#9C9488]" style={{ width: 40 }}>{s}</span>)}
                    </div>
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
