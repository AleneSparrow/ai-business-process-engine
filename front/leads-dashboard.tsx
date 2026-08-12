import React, { useState, useMemo } from "react";
import {
  Search, Bell, ChevronDown, MessageSquare, Users, Workflow,
  Settings, LayoutGrid, Phone, Mail, Clock, ArrowUpRight,
  CircleDot, Check, AlertTriangle, X
} from "lucide-react";

/* ---------------------------------------------------------
   Design tokens
   Background   #F7F6F2  (warm paper, not the AI-cliché cream)
   Surface      #FFFFFF
   Ink primary  #171A21
   Ink muted    #6B7280
   Line         #E7E5DE
   Accent       #3A3EA6  (confident indigo — used sparingly)
   Amber (attn) #C97A1F
   Green (ok)   #1E7B52
   Red (lost)   #B4483A
   Display face: "Space Grotesk"  — geometric, a little mechanical
   Body face:    "Inter"
   Mono/utility: "IBM Plex Mono" — timestamps, IDs
--------------------------------------------------------- */

const STAGES = ["Trigger", "Context", "Decision", "Action", "Result"];

const STATE_META = {
  NEW: { label: "New", color: "#6B7280", bg: "#F1F1EF" },
  QUALIFYING: { label: "Qualifying", color: "#3A3EA6", bg: "#EEEEF9" },
  NEEDS_HUMAN: { label: "Needs you", color: "#C97A1F", bg: "#FBF0E2" },
  BOOKED: { label: "Booked", color: "#1E7B52", bg: "#E9F5EF" },
  LOST: { label: "Lost", color: "#B4483A", bg: "#FBEBE9" },
  COMPLETED: { label: "Completed", color: "#171A21", bg: "#F1F1EF" },
};

const CASES = [
  {
    id: "CS-1042",
    name: "Marcus Webb",
    service: "Furnace diagnostic",
    channel: "Web chat",
    state: "NEEDS_HUMAN",
    stage: 2,
    detail: "Asked for a price before confirming service address",
    time: "2m ago",
  },
  {
    id: "CS-1041",
    name: "Priya Anand",
    service: "Drain cleaning",
    channel: "SMS",
    state: "BOOKED",
    stage: 4,
    detail: "Confirmed Thursday 9–11am window",
    time: "14m ago",
  },
  {
    id: "CS-1040",
    name: "Dana Okafor",
    service: "AC repair",
    channel: "Web chat",
    state: "QUALIFYING",
    stage: 1,
    detail: "Waiting on unit age and zip code",
    time: "22m ago",
  },
  {
    id: "CS-1039",
    name: "Leon Frei",
    service: "Water heater install",
    channel: "SMS",
    state: "QUALIFYING",
    stage: 1,
    detail: "Outside standard service radius — checking",
    time: "41m ago",
  },
  {
    id: "CS-1038",
    name: "Ines Roth",
    service: "Furnace diagnostic",
    channel: "Web chat",
    state: "COMPLETED",
    stage: 4,
    detail: "Job closed, review request sent",
    time: "1h ago",
  },
  {
    id: "CS-1037",
    name: "Wyatt Chen",
    service: "Drain cleaning",
    channel: "SMS",
    state: "LOST",
    stage: 2,
    detail: "Went with another provider",
    time: "3h ago",
  },
];

function Stepper({ stage, state }) {
  const color = STATE_META[state].color;
  return (
    <div className="flex items-center gap-1.5" aria-label={`Pipeline stage: ${STAGES[stage]}`}>
      {STAGES.map((label, i) => {
        const done = i < stage;
        const active = i === stage;
        return (
          <div key={label} className="flex items-center gap-1.5">
            <div
              className="w-2 h-2 rounded-full transition-colors"
              style={{
                backgroundColor: done || active ? color : "#DEDBD2",
                boxShadow: active ? `0 0 0 3px ${color}22` : "none",
              }}
              title={label}
            />
            {i < STAGES.length - 1 && (
              <div
                className="h-px w-4"
                style={{ backgroundColor: i < stage ? color : "#DEDBD2" }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

function StatePill({ state }) {
  const m = STATE_META[state];
  return (
    <span
      className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium"
      style={{ color: m.color, backgroundColor: m.bg }}
    >
      {m.label}
    </span>
  );
}

function NavItem({ icon: Icon, label, active }) {
  return (
    <button
      className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors"
      style={{
        color: active ? "#171A21" : "#6B7280",
        backgroundColor: active ? "#EEEEF9" : "transparent",
        fontWeight: active ? 600 : 500,
      }}
    >
      <Icon size={17} strokeWidth={2} />
      {label}
    </button>
  );
}

function StatCard({ label, value, sub, tone }) {
  return (
    <div className="bg-white rounded-2xl border border-[#E7E5DE] px-5 py-4 flex-1 min-w-[150px]">
      <div className="text-xs font-medium text-[#6B7280] mb-1.5">{label}</div>
      <div className="flex items-baseline gap-2">
        <span
          className="text-[26px] leading-none"
          style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}
        >
          {value}
        </span>
        {sub && (
          <span className="text-xs font-medium" style={{ color: tone || "#6B7280" }}>
            {sub}
          </span>
        )}
      </div>
    </div>
  );
}

export default function LeadsDashboard() {
  const [filter, setFilter] = useState("ALL");
  const [selected, setSelected] = useState(CASES[0]);

  const filtered = useMemo(
    () => (filter === "ALL" ? CASES : CASES.filter((c) => c.state === filter)),
    [filter]
  );

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
    <div
      className="min-h-screen w-full flex"
      style={{ backgroundColor: "#F7F6F2", fontFamily: "'Inter', sans-serif", color: "#171A21" }}
    >
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
        * { box-sizing: border-box; }
        ::selection { background: #3A3EA633; }
      `}</style>

      {/* Sidebar */}
      <aside className="w-60 shrink-0 border-r border-[#E7E5DE] px-4 py-5 hidden md:flex md:flex-col justify-between">
        <div>
          <div className="flex items-center gap-2 px-2 mb-8">
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center text-white text-xs font-bold"
              style={{ backgroundColor: "#3A3EA6", fontFamily: "'Space Grotesk', sans-serif" }}
            >
              A
            </div>
            <div>
              <div className="text-sm font-semibold leading-tight">Acme Home Services</div>
              <div className="text-[11px] text-[#6B7280] leading-tight">Business DNA v3</div>
            </div>
          </div>
          <nav className="flex flex-col gap-1">
            <NavItem icon={LayoutGrid} label="Overview" />
            <NavItem icon={Users} label="Leads & cases" active />
            <NavItem icon={MessageSquare} label="Conversations" />
            <NavItem icon={Workflow} label="Business DNA" />
            <NavItem icon={Settings} label="Settings" />
          </nav>
        </div>
        <div className="px-2 text-[11px] text-[#9AA1AC] leading-relaxed">
          Every step your engine takes — logged, reversible, never silent.
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 min-w-0 flex flex-col">
        {/* Top bar */}
        <header className="flex items-center justify-between px-6 md:px-8 py-4 border-b border-[#E7E5DE]">
          <div>
            <h1
              className="text-xl"
              style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}
            >
              Leads & cases
            </h1>
            <p className="text-sm text-[#6B7280] mt-0.5">
              Every conversation your engine has handled since 8:00am
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="relative hidden sm:block">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9AA1AC]" />
              <input
                placeholder="Search leads..."
                className="pl-9 pr-3 py-2 rounded-lg bg-white border border-[#E7E5DE] text-sm w-52 outline-none focus:ring-2 focus:ring-[#3A3EA633]"
              />
            </div>
            <button className="relative w-9 h-9 rounded-lg bg-white border border-[#E7E5DE] flex items-center justify-center">
              <Bell size={16} strokeWidth={2} />
              <span
                className="absolute -top-1 -right-1 w-4 h-4 rounded-full text-[10px] flex items-center justify-center text-white font-medium"
                style={{ backgroundColor: "#C97A1F" }}
              >
                {counts.needsHuman}
              </span>
            </button>
          </div>
        </header>

        <div className="p-6 md:p-8 flex flex-col gap-6">
          {/* Stats */}
          <div className="flex flex-wrap gap-3">
            <StatCard label="Needs your attention" value={counts.needsHuman} sub="respond soon" tone="#C97A1F" />
            <StatCard label="Qualifying now" value={counts.qualifying} sub="engine working" tone="#3A3EA6" />
            <StatCard label="Booked this week" value={counts.booked} sub="+2 vs last wk" tone="#1E7B52" />
            <StatCard label="Avg. reply time" value="38s" sub="engine-side" />
          </div>

          <div className="flex flex-col lg:flex-row gap-6">
            {/* List */}
            <div className="flex-1 min-w-0 bg-white rounded-2xl border border-[#E7E5DE] overflow-hidden">
              <div className="flex items-center gap-2 px-5 py-3 border-b border-[#E7E5DE] overflow-x-auto">
                {["ALL", "NEEDS_HUMAN", "QUALIFYING", "BOOKED", "LOST", "COMPLETED"].map((s) => (
                  <button
                    key={s}
                    onClick={() => setFilter(s)}
                    className="px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors"
                    style={{
                      backgroundColor: filter === s ? "#171A21" : "transparent",
                      color: filter === s ? "#fff" : "#6B7280",
                    }}
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
                    style={{
                      backgroundColor: selected.id === c.id ? "#FAFAF7" : "transparent",
                    }}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-sm font-semibold truncate">{c.name}</span>
                          <span
                            className="text-[11px] text-[#9AA1AC]"
                            style={{ fontFamily: "'IBM Plex Mono', monospace" }}
                          >
                            {c.id}
                          </span>
                        </div>
                        <div className="text-sm text-[#6B7280] truncate">{c.service} · {c.detail}</div>
                      </div>
                      <div className="flex flex-col items-end gap-2 shrink-0">
                        <StatePill state={c.state} />
                        <span className="text-[11px] text-[#9AA1AC] flex items-center gap-1">
                          <Clock size={11} /> {c.time}
                        </span>
                      </div>
                    </div>
                    <div className="mt-3">
                      <Stepper stage={c.stage} state={c.state} />
                    </div>
                  </li>
                ))}
              </ul>
            </div>

            {/* Detail panel */}
            <div className="w-full lg:w-80 shrink-0 bg-white rounded-2xl border border-[#E7E5DE] p-5 h-fit sticky top-6">
              <div className="flex items-center justify-between mb-4">
                <span
                  className="text-[11px] uppercase tracking-wide text-[#9AA1AC] font-medium"
                  style={{ fontFamily: "'IBM Plex Mono', monospace" }}
                >
                  {selected.id}
                </span>
                <StatePill state={selected.state} />
              </div>
              <h2 className="text-lg font-semibold mb-1">{selected.name}</h2>
              <p className="text-sm text-[#6B7280] mb-4">{selected.service} · {selected.channel}</p>

              <div className="mb-5">
                <div className="text-xs font-medium text-[#9AA1AC] mb-2">Where this case is</div>
                <Stepper stage={selected.stage} state={selected.state} />
                <div className="flex justify-between mt-1.5">
                  {STAGES.map((s) => (
                    <span key={s} className="text-[10px] text-[#9AA1AC]" style={{ width: 40 }}>
                      {s}
                    </span>
                  ))}
                </div>
              </div>

              <div className="rounded-xl p-3 mb-5" style={{ backgroundColor: "#FAFAF7" }}>
                <p className="text-sm leading-relaxed">{selected.detail}</p>
              </div>

              {selected.state === "NEEDS_HUMAN" ? (
                <div className="flex flex-col gap-2">
                  <button
                    className="w-full py-2.5 rounded-lg text-sm font-medium text-white flex items-center justify-center gap-2"
                    style={{ backgroundColor: "#171A21" }}
                  >
                    Open conversation <ArrowUpRight size={14} />
                  </button>
                  <button className="w-full py-2.5 rounded-lg text-sm font-medium border border-[#E7E5DE]">
                    Mark resolved
                  </button>
                </div>
              ) : (
                <button className="w-full py-2.5 rounded-lg text-sm font-medium border border-[#E7E5DE] flex items-center justify-center gap-2">
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
