import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search, Bell, ArrowUpRight, Clock, Phone, Mail, Loader2 } from "lucide-react";
import { Sidebar } from "../components/Sidebar";
import { useAuth, describeError } from "../auth/AuthContext";
import { api, type DashboardCaseSummary } from "../api/client";
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
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<CaseState | "ALL">("ALL");
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
    return () => {
      cancelled = true;
    };
  }, [token, businessId]);

  const decorated = useMemo(
    () =>
      (cases ?? []).map((c) => {
        const { caseState, stage } = mapProcessState(c.current_state);
        const detail = c.latest_event_type ? describeEvent(c.latest_event_type).label : "No activity yet";
        return { ...c, caseState, stage, detail };
      }),
    [cases],
  );

  const filtered = useMemo(
    () => (filter === "ALL" ? decorated : decorated.filter((c) => c.caseState === filter)),
    [decorated, filter],
  );

  const selected = useMemo(
    () => decorated.find((c) => c.case_id === selectedId) ?? decorated[0] ?? null,
    [decorated, selectedId],
  );

  const counts = useMemo(() => {
    const c = { needsHuman: 0, booked: 0, qualifying: 0 };
    decorated.forEach((x) => {
      if (x.caseState === "NEEDS_HUMAN") c.needsHuman++;
      if (x.caseState === "BOOKED") c.booked++;
      if (x.caseState === "QUALIFYING") c.qualifying++;
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
              <input placeholder="Search leads..." className="pl-9 pr-3 py-2 rounded-lg bg-white border border-[#E7E5DE] text-sm w-52 outline-none focus:ring-2 focus:ring-[#B8733333]" />
            </div>
            <button className="relative w-9 h-9 rounded-lg bg-white border border-[#E7E5DE] flex items-center justify-center">
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
            <StatCard label="Total cases" value={decorated.length} />
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
                <div className="flex items-center gap-2 px-5 py-3 border-b border-[#E7E5DE] overflow-x-auto">
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
                <ul>
                  {filtered.map((c) => (
                    <li
                      key={c.case_id}
                      onClick={() => setSelectedId(c.case_id)}
                      className="px-5 py-4 border-b border-[#F0EFE9] last:border-0 cursor-pointer transition-colors"
                      style={{ backgroundColor: selected?.case_id === c.case_id ? "#FAFAF7" : "transparent" }}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-sm font-semibold truncate">{c.lead.name || "Unnamed lead"}</span>
                            <span className="text-[11px] text-[#9C9488]" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>{c.case_id.slice(0, 8)}</span>
                          </div>
                          <div className="text-sm text-[#6B6459] truncate">{c.detail}</div>
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
