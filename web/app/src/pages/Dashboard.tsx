import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search, Bell, ArrowUpRight, Clock, MessageSquare, Phone, Mail } from "lucide-react";
import { Sidebar } from "../components/Sidebar";
import { STAGES, STATE_META, Stepper, StatePill, PreviewBanner, type CaseState } from "../components/Shared";

/**
 * Preview data — ported verbatim from the prototype. There is no staff dashboard/
 * conversation API yet (Milestone 8 slice 2), so this screen renders illustrative
 * cases rather than a live feed from your account.
 */
const CASES: { id: string; name: string; service: string; channel: string; state: CaseState; stage: number; detail: string; time: string }[] = [
  { id: "CS-1042", name: "Marcus Webb", service: "Furnace diagnostic", channel: "Web chat", state: "NEEDS_HUMAN", stage: 2, detail: "Asked for a price before confirming service address", time: "2m ago" },
  { id: "CS-1041", name: "Priya Anand", service: "Drain cleaning", channel: "SMS", state: "BOOKED", stage: 4, detail: "Confirmed Thursday 9–11am window", time: "14m ago" },
  { id: "CS-1040", name: "Dana Okafor", service: "AC repair", channel: "Web chat", state: "QUALIFYING", stage: 1, detail: "Waiting on unit age and zip code", time: "22m ago" },
  { id: "CS-1039", name: "Leon Frei", service: "Water heater install", channel: "SMS", state: "QUALIFYING", stage: 1, detail: "Outside standard service radius — checking", time: "41m ago" },
  { id: "CS-1038", name: "Ines Roth", service: "Furnace diagnostic", channel: "Web chat", state: "COMPLETED", stage: 4, detail: "Job closed, review request sent", time: "1h ago" },
  { id: "CS-1037", name: "Wyatt Chen", service: "Drain cleaning", channel: "SMS", state: "LOST", stage: 2, detail: "Went with another provider", time: "3h ago" },
];

const FILTERS: (CaseState | "ALL")[] = ["ALL", "NEEDS_HUMAN", "QUALIFYING", "BOOKED", "LOST", "COMPLETED"];

function StatCard({ label, value, sub, tone }: { label: string; value: string | number; sub?: string; tone?: string }) {
  return (
    <div className="bg-white rounded-2xl border border-[#E7E5DE] px-5 py-4 flex-1 min-w-[150px]">
      <div className="text-xs font-medium text-[#6B7280] mb-1.5">{label}</div>
      <div className="flex items-baseline gap-2">
        <span className="text-[26px] leading-none" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>{value}</span>
        {sub && <span className="text-xs font-medium" style={{ color: tone || "#6B7280" }}>{sub}</span>}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState<CaseState | "ALL">("ALL");
  const [selected, setSelected] = useState(CASES[0]);
  const filtered = useMemo(() => (filter === "ALL" ? CASES : CASES.filter((c) => c.state === filter)), [filter]);
  const counts = useMemo(() => {
    const c = { needsHuman: 0, booked: 0, qualifying: 0 };
    CASES.forEach((x) => {
      if (x.state === "NEEDS_HUMAN") c.needsHuman++;
      if (x.state === "BOOKED") c.booked++;
      if (x.state === "QUALIFYING") c.qualifying++;
    });
    return c;
  }, []);

  return (
    <div className="min-h-screen w-full flex" style={{ backgroundColor: "#F7F6F2", fontFamily: "'Inter', sans-serif", color: "#171A21" }}>
      <Sidebar />
      <main className="flex-1 min-w-0 flex flex-col">
        <PreviewBanner text="Preview data — the live cases feed ships with the staff dashboard API (next milestone)." />
        <header className="flex items-center justify-between px-6 md:px-8 py-4 border-b border-[#E7E5DE]">
          <div>
            <h1 className="text-xl" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>Leads & cases</h1>
            <p className="text-sm text-[#6B7280] mt-0.5">Every conversation your engine has handled since 8:00am</p>
          </div>
          <div className="flex items-center gap-3">
            <div className="relative hidden sm:block">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9AA1AC]" />
              <input placeholder="Search leads..." className="pl-9 pr-3 py-2 rounded-lg bg-white border border-[#E7E5DE] text-sm w-52 outline-none focus:ring-2 focus:ring-[#3A3EA633]" />
            </div>
            <button className="relative w-9 h-9 rounded-lg bg-white border border-[#E7E5DE] flex items-center justify-center">
              <Bell size={16} strokeWidth={2} />
              <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full text-[10px] flex items-center justify-center text-white font-medium" style={{ backgroundColor: "#C97A1F" }}>{counts.needsHuman}</span>
            </button>
          </div>
        </header>

        <div className="p-6 md:p-8 flex flex-col gap-6">
          <div className="flex flex-wrap gap-3">
            <StatCard label="Needs your attention" value={counts.needsHuman} sub="respond soon" tone="#C97A1F" />
            <StatCard label="Qualifying now" value={counts.qualifying} sub="engine working" tone="#3A3EA6" />
            <StatCard label="Booked this week" value={counts.booked} sub="+2 vs last wk" tone="#1E7B52" />
            <StatCard label="Avg. reply time" value="38s" sub="engine-side" />
          </div>

          <div className="flex flex-col lg:flex-row gap-6">
            <div className="flex-1 min-w-0 bg-white rounded-2xl border border-[#E7E5DE] overflow-hidden">
              <div className="flex items-center gap-2 px-5 py-3 border-b border-[#E7E5DE] overflow-x-auto">
                {FILTERS.map((s) => (
                  <button
                    key={s}
                    onClick={() => setFilter(s)}
                    className="px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors"
                    style={{ backgroundColor: filter === s ? "#171A21" : "transparent", color: filter === s ? "#fff" : "#6B7280" }}
                  >
                    {s === "ALL" ? "All" : STATE_META[s].label}
                  </button>
                ))}
              </div>
              <ul>
                {filtered.map((c) => (
                  <li
                    key={c.id}
                    onClick={() => setSelected(c)}
                    className="px-5 py-4 border-b border-[#F0EFE9] last:border-0 cursor-pointer transition-colors"
                    style={{ backgroundColor: selected.id === c.id ? "#FAFAF7" : "transparent" }}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-sm font-semibold truncate">{c.name}</span>
                          <span className="text-[11px] text-[#9AA1AC]" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>{c.id}</span>
                        </div>
                        <div className="text-sm text-[#6B7280] truncate">{c.service} · {c.detail}</div>
                      </div>
                      <div className="flex flex-col items-end gap-2 shrink-0">
                        <StatePill state={c.state} />
                        <span className="text-[11px] text-[#9AA1AC] flex items-center gap-1"><Clock size={11} /> {c.time}</span>
                      </div>
                    </div>
                    <div className="mt-3"><Stepper stage={c.stage} color={STATE_META[c.state].color} /></div>
                  </li>
                ))}
              </ul>
            </div>

            <div className="w-full lg:w-80 shrink-0 bg-white rounded-2xl border border-[#E7E5DE] p-5 h-fit sticky top-6">
              <div className="flex items-center justify-between mb-4">
                <span className="text-[11px] uppercase tracking-wide text-[#9AA1AC] font-medium" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>{selected.id}</span>
                <StatePill state={selected.state} />
              </div>
              <h2 className="text-lg font-semibold mb-1">{selected.name}</h2>
              <p className="text-sm text-[#6B7280] mb-4">{selected.service} · {selected.channel}</p>
              <div className="mb-5">
                <div className="text-xs font-medium text-[#9AA1AC] mb-2">Where this case is</div>
                <Stepper stage={selected.stage} color={STATE_META[selected.state].color} />
                <div className="flex justify-between mt-1.5">
                  {STAGES.map((s) => <span key={s} className="text-[10px] text-[#9AA1AC]" style={{ width: 40 }}>{s}</span>)}
                </div>
              </div>
              <div className="rounded-xl p-3 mb-5" style={{ backgroundColor: "#FAFAF7" }}>
                <p className="text-sm leading-relaxed">{selected.detail}</p>
              </div>
              {selected.state === "NEEDS_HUMAN" ? (
                <div className="flex flex-col gap-2">
                  <button onClick={() => navigate("/app/conversations")} className="w-full py-2.5 rounded-lg text-sm font-medium text-white flex items-center justify-center gap-2" style={{ backgroundColor: "#171A21" }}>
                    Open conversation <ArrowUpRight size={14} />
                  </button>
                  <button className="w-full py-2.5 rounded-lg text-sm font-medium border border-[#E7E5DE]">Mark resolved</button>
                </div>
              ) : (
                <button onClick={() => navigate("/app/conversations")} className="w-full py-2.5 rounded-lg text-sm font-medium border border-[#E7E5DE] flex items-center justify-center gap-2">
                  <MessageSquare size={14} /> View full conversation
                </button>
              )}
              <div className="mt-5 pt-4 border-t border-[#F0EFE9] flex items-center gap-4 text-xs text-[#6B7280]">
                <span className="flex items-center gap-1.5"><Phone size={12} /> On file</span>
                <span className="flex items-center gap-1.5"><Mail size={12} /> On file</span>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
