import React, { useState, useMemo } from "react";
import {
  ArrowRight, ArrowLeft, MessageSquare, Workflow, ShieldCheck, Zap, ChevronRight,
  Check, Menu, X, Search, Bell, LayoutGrid, Users, Settings as SettingsIcon,
  Phone, Mail, ArrowUpRight, Clock, Plus, Send, ShieldAlert, RotateCcw, Building2,
  Wrench, MapPin, MessageCircleQuestion, Sparkles,
} from "lucide-react";

/* ============================================================
   DESIGN SYSTEM — shared across every screen in this prototype
   Background #F7F6F2 · Surface #FFFFFF · Ink #171A21 · Muted #6B7280
   Line #E7E5DE · Accent indigo #3A3EA6 · Amber #C97A1F
   Green #1E7B52 · Red #B4483A
   Display: Space Grotesk · Body: Inter · Utility: IBM Plex Mono
   ============================================================ */

const STAGES = ["Trigger", "Context", "Decision", "Action", "Result"];

const STATE_META = {
  NEW: { label: "New", color: "#6B7280", bg: "#F1F1EF" },
  QUALIFYING: { label: "Qualifying", color: "#3A3EA6", bg: "#EEEEF9" },
  NEEDS_HUMAN: { label: "Needs you", color: "#C97A1F", bg: "#FBF0E2" },
  BOOKED: { label: "Booked", color: "#1E7B52", bg: "#E9F5EF" },
  LOST: { label: "Lost", color: "#B4483A", bg: "#FBEBE9" },
  COMPLETED: { label: "Completed", color: "#171A21", bg: "#F1F1EF" },
};

function GlobalStyle() {
  return (
    <style>{`
      @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');
      * { box-sizing: border-box; }
      .dna-fade { animation: dnaFade 0.25s ease; }
      @keyframes dnaFade { from { opacity: 0; transform: translateY(3px); } to { opacity: 1; transform: translateY(0); } }
    `}</style>
  );
}

function Stepper({ stage, color = "#3A3EA6" }) {
  return (
    <div className="flex items-center gap-1.5">
      {STAGES.map((label, i) => (
        <div key={label} className="flex items-center gap-1.5">
          <div
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: i <= stage ? color : "#DEDBD2", boxShadow: i === stage ? `0 0 0 3px ${color}22` : "none" }}
            title={label}
          />
          {i < STAGES.length - 1 && <div className="h-px w-4" style={{ backgroundColor: i < stage ? color : "#DEDBD2" }} />}
        </div>
      ))}
    </div>
  );
}

function StatePill({ state }) {
  const m = STATE_META[state];
  return (
    <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium" style={{ color: m.color, backgroundColor: m.bg }}>
      {m.label}
    </span>
  );
}

function NavItem({ icon: Icon, label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors text-left"
      style={{ color: active ? "#171A21" : "#6B7280", backgroundColor: active ? "#EEEEF9" : "transparent", fontWeight: active ? 600 : 500 }}
    >
      <Icon size={17} strokeWidth={2} />
      {label}
    </button>
  );
}

function Sidebar({ view, setView }) {
  return (
    <aside className="w-60 shrink-0 border-r border-[#E7E5DE] px-4 py-5 hidden md:flex md:flex-col justify-between">
      <div>
        <button onClick={() => setView("dashboard")} className="flex items-center gap-2 px-2 mb-8">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center text-white text-xs font-bold" style={{ backgroundColor: "#3A3EA6", fontFamily: "'Space Grotesk', sans-serif" }}>A</div>
          <div className="text-left">
            <div className="text-sm font-semibold leading-tight">Acme Home Services</div>
            <div className="text-[11px] text-[#6B7280] leading-tight">Business DNA v3</div>
          </div>
        </button>
        <nav className="flex flex-col gap-1">
          <NavItem icon={LayoutGrid} label="Overview" active={view === "dashboard"} onClick={() => setView("dashboard")} />
          <NavItem icon={Users} label="Leads & cases" active={view === "dashboard"} onClick={() => setView("dashboard")} />
          <NavItem icon={MessageSquare} label="Conversations" active={view === "conversation"} onClick={() => setView("conversation")} />
          <NavItem icon={Workflow} label="Business DNA" active={view === "settings"} onClick={() => setView("settings")} />
          <NavItem icon={SettingsIcon} label="Settings" active={false} onClick={() => setView("settings")} />
        </nav>
      </div>
      <div className="px-2 text-[11px] text-[#9AA1AC] leading-relaxed">
        Every step your engine takes — logged, reversible, never silent.
      </div>
    </aside>
  );
}

/* ============================================================
   LANDING
   ============================================================ */

function ChatBubble() {
  const [step, setStep] = useState(2);
  return (
    <div className="bg-white rounded-2xl border border-[#E7E5DE] shadow-[0_1px_2px_rgba(0,0,0,0.03)] p-5 w-full max-w-sm">
      <div className="flex items-center justify-between mb-4">
        <span className="text-xs font-medium text-[#9AA1AC]" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>acme-home-services · web chat</span>
        <Stepper stage={step} />
      </div>
      <div className="flex flex-col gap-2.5">
        <div className="self-start bg-[#F1F1EF] rounded-2xl rounded-bl-sm px-3.5 py-2.5 text-sm max-w-[85%]">
          Hi, my furnace is making a rattling noise, can someone come look today?
        </div>
        <div className="self-end text-white rounded-2xl rounded-br-sm px-3.5 py-2.5 text-sm max-w-[85%]" style={{ backgroundColor: "#3A3EA6" }}>
          I can get that scheduled. What's the service zip code, and is anyone home this afternoon?
        </div>
        <div className="self-start bg-[#F1F1EF] rounded-2xl rounded-bl-sm px-3.5 py-2.5 text-sm max-w-[85%]">
          60601, yes I'll be home after 2pm
        </div>
      </div>
      <button onClick={() => setStep((s) => (s < 4 ? s + 1 : 2))} className="mt-4 text-xs font-medium text-[#3A3EA6] flex items-center gap-1">
        Advance step <ChevronRight size={12} />
      </button>
    </div>
  );
}

function StatBlock({ n, label }) {
  return (
    <div>
      <div style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }} className="text-3xl mb-1">{n}</div>
      <div className="text-sm text-[#6B7280]">{label}</div>
    </div>
  );
}

function FeatureCard({ icon: Icon, title, body }) {
  return (
    <div className="bg-white rounded-2xl border border-[#E7E5DE] p-6">
      <div className="w-9 h-9 rounded-lg flex items-center justify-center mb-4" style={{ backgroundColor: "#EEEEF9" }}>
        <Icon size={17} color="#3A3EA6" strokeWidth={2} />
      </div>
      <h3 className="font-semibold mb-1.5">{title}</h3>
      <p className="text-sm text-[#6B7280] leading-relaxed">{body}</p>
    </div>
  );
}

function StepRow({ n, title, body, last }) {
  return (
    <div className="flex gap-5">
      <div className="flex flex-col items-center">
        <div className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold shrink-0" style={{ backgroundColor: "#171A21", color: "#fff", fontFamily: "'Space Grotesk', sans-serif" }}>{n}</div>
        {!last && <div className="w-px flex-1 bg-[#E7E5DE] my-1" />}
      </div>
      <div className="pb-10">
        <h3 className="font-semibold mb-1.5">{title}</h3>
        <p className="text-sm text-[#6B7280] leading-relaxed max-w-md">{body}</p>
      </div>
    </div>
  );
}

function LandingScreen({ setView }) {
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <div style={{ backgroundColor: "#F7F6F2", fontFamily: "'Inter', sans-serif", color: "#171A21" }} className="min-h-screen w-full">
      <header className="sticky top-0 z-20 backdrop-blur-sm" style={{ backgroundColor: "#F7F6F2EE", borderBottom: "1px solid #E7E5DE" }}>
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg flex items-center justify-center text-white text-xs font-bold" style={{ backgroundColor: "#3A3EA6", fontFamily: "'Space Grotesk', sans-serif" }}>A</div>
            <span className="font-semibold text-sm" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>Atelier</span>
          </div>
          <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-[#6B7280]">
            <a href="#how" className="hover:text-[#171A21] transition-colors">How it works</a>
            <a href="#features" className="hover:text-[#171A21] transition-colors">Features</a>
            <a href="#trust" className="hover:text-[#171A21] transition-colors">Trust & audit</a>
          </nav>
          <div className="hidden md:flex items-center gap-3">
            <button onClick={() => setView("dashboard")} className="text-sm font-medium text-[#6B7280]">Sign in</button>
            <button onClick={() => setView("onboarding")} className="text-sm font-medium text-white px-4 py-2 rounded-lg flex items-center gap-1.5" style={{ backgroundColor: "#171A21" }}>
              Get started <ArrowRight size={14} />
            </button>
          </div>
          <button className="md:hidden" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X size={20} /> : <Menu size={20} />}</button>
        </div>
        {menuOpen && (
          <div className="md:hidden px-6 pb-4 flex flex-col gap-3 text-sm font-medium text-[#6B7280]">
            <a href="#how">How it works</a>
            <a href="#features">Features</a>
            <a href="#trust">Trust & audit</a>
            <button onClick={() => setView("onboarding")} className="text-white px-4 py-2 rounded-lg mt-1" style={{ backgroundColor: "#171A21" }}>Get started</button>
          </div>
        )}
      </header>

      <section className="max-w-6xl mx-auto px-6 pt-16 md:pt-24 pb-16 grid md:grid-cols-2 gap-12 items-center">
        <div>
          <div className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full mb-6" style={{ backgroundColor: "#EEEEF9", color: "#3A3EA6" }}>
            <Zap size={12} /> Built for service businesses
          </div>
          <h1 className="text-4xl md:text-5xl leading-[1.08] mb-5" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>
            Every lead gets answered.<br />Every step gets logged.
          </h1>
          <p className="text-base text-[#6B7280] leading-relaxed mb-8 max-w-md">
            Atelier qualifies, books, and follows up with your customers the moment they message —
            then hands off to you the moment it should. Nothing happens off the record.
          </p>
          <div className="flex flex-wrap items-center gap-3 mb-10">
            <button onClick={() => setView("onboarding")} className="text-sm font-medium text-white px-5 py-3 rounded-lg flex items-center gap-2" style={{ backgroundColor: "#171A21" }}>
              Set up your business <ArrowRight size={15} />
            </button>
            <button onClick={() => setView("conversation")} className="text-sm font-medium px-5 py-3 rounded-lg border border-[#E7E5DE] bg-white">
              See a live conversation
            </button>
          </div>
          <div className="flex gap-10">
            <StatBlock n="38s" label="Avg. first reply" />
            <StatBlock n="100%" label="Steps audited" />
            <StatBlock n="0" label="Silent AI actions" />
          </div>
        </div>
        <div className="flex justify-center md:justify-end"><ChatBubble /></div>
      </section>

      <section className="border-y border-[#E7E5DE] bg-white">
        <div className="max-w-6xl mx-auto px-6 py-6 flex items-center justify-center gap-3 text-sm text-[#9AA1AC]">
          <ShieldCheck size={15} /> Every decision your engine makes is deterministic, reviewable, and reversible — never a black box.
        </div>
      </section>

      <section id="how" className="max-w-6xl mx-auto px-6 py-20 md:py-28">
        <div className="max-w-lg mb-14">
          <span className="text-xs font-medium text-[#3A3EA6] uppercase tracking-wide">How it works</span>
          <h2 className="text-3xl mt-2" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>One path, five steps, no surprises</h2>
        </div>
        <div className="grid md:grid-cols-2 gap-x-16">
          <div>
            <StepRow n="1" title="A customer messages your business" body="Through your website chat or a text — Atelier picks it up the moment it arrives." />
            <StepRow n="2" title="It qualifies against your rules" body="Service area, required details, urgency — defined by you, applied every time, the same way." />
            <StepRow n="3" title="It decides, or it asks you" body="Clear cases move forward on their own. Anything ambiguous escalates to you, in plain language." last />
          </div>
          <div className="mt-2 md:mt-[52px]">
            <StepRow n="4" title="It books, quotes, or follows up" body="The action your rules allow — never more, never assumed." />
            <StepRow n="5" title="Every step stays on the record" body="You can open any case and see exactly what happened, in order, at any time." last />
          </div>
        </div>
      </section>

      <section id="features" className="max-w-6xl mx-auto px-6 pb-20 md:pb-28">
        <div className="grid md:grid-cols-3 gap-5">
          <FeatureCard icon={MessageSquare} title="Answers instantly, in your voice" body="Configured tone, language, and channel per business — customers never feel handed to a machine." />
          <FeatureCard icon={Workflow} title="Runs your process, not a generic script" body="Business DNA encodes your services, questions, and escalation rules — no two setups behave alike." />
          <FeatureCard icon={ShieldCheck} title="Escalates instead of guessing" body="When something falls outside your rules, it stops and asks — it never improvises a commitment." />
        </div>
      </section>

      <section id="trust" className="bg-white border-y border-[#E7E5DE]">
        <div className="max-w-6xl mx-auto px-6 py-20 md:py-24 grid md:grid-cols-2 gap-12 items-center">
          <div>
            <span className="text-xs font-medium text-[#3A3EA6] uppercase tracking-wide">Trust & audit</span>
            <h2 className="text-3xl mt-2 mb-5" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>Nothing your engine does is invisible</h2>
            <ul className="flex flex-col gap-3.5">
              {[
                "Every trigger, decision, and action is written to an append-only history",
                "AI drafts wording — it never bypasses your workflow or risk rules",
                "You can trace any booking, quote, or reply back to the exact step that produced it",
              ].map((t) => (
                <li key={t} className="flex items-start gap-2.5 text-sm text-[#171A21]">
                  <Check size={16} className="mt-0.5 shrink-0" color="#1E7B52" /> {t}
                </li>
              ))}
            </ul>
          </div>
          <div className="bg-[#F7F6F2] rounded-2xl border border-[#E7E5DE] p-5">
            <div className="text-xs font-medium text-[#9AA1AC] mb-3" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>CS-1042 · audit trail</div>
            <div className="flex flex-col gap-2.5 text-sm">
              {[
                ["09:41:02", "Trigger", "Inbound web chat message received"],
                ["09:41:03", "Context", "Matched existing lead by phone"],
                ["09:41:04", "Decision", "Missing required field: service zip"],
                ["09:41:04", "Action", "Sent clarifying question"],
                ["09:44:18", "Result", "Escalated — outside standard radius"],
              ].map(([time, stage, desc]) => (
                <div key={stage} className="flex gap-3">
                  <span className="text-[#9AA1AC] shrink-0" style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 12 }}>{time}</span>
                  <span className="font-medium shrink-0 w-16">{stage}</span>
                  <span className="text-[#6B7280]">{desc}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-6 py-20 md:py-28 text-center">
        <h2 className="text-3xl md:text-4xl mb-4" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>Your first customer is already messaging someone.</h2>
        <p className="text-[#6B7280] mb-8 max-w-md mx-auto">Set up your Business DNA in minutes and give every lead a same-minute answer.</p>
        <button onClick={() => setView("onboarding")} className="text-sm font-medium text-white px-6 py-3.5 rounded-lg inline-flex items-center gap-2" style={{ backgroundColor: "#171A21" }}>
          Set up your business <ArrowRight size={15} />
        </button>
      </section>

      <footer className="border-t border-[#E7E5DE] py-8">
        <div className="max-w-6xl mx-auto px-6 flex items-center justify-between text-xs text-[#9AA1AC]">
          <span>© 2026 Atelier</span>
          <span>Deterministic by design</span>
        </div>
      </footer>
    </div>
  );
}

/* ============================================================
   DASHBOARD
   ============================================================ */

const CASES = [
  { id: "CS-1042", name: "Marcus Webb", service: "Furnace diagnostic", channel: "Web chat", state: "NEEDS_HUMAN", stage: 2, detail: "Asked for a price before confirming service address", time: "2m ago" },
  { id: "CS-1041", name: "Priya Anand", service: "Drain cleaning", channel: "SMS", state: "BOOKED", stage: 4, detail: "Confirmed Thursday 9–11am window", time: "14m ago" },
  { id: "CS-1040", name: "Dana Okafor", service: "AC repair", channel: "Web chat", state: "QUALIFYING", stage: 1, detail: "Waiting on unit age and zip code", time: "22m ago" },
  { id: "CS-1039", name: "Leon Frei", service: "Water heater install", channel: "SMS", state: "QUALIFYING", stage: 1, detail: "Outside standard service radius — checking", time: "41m ago" },
  { id: "CS-1038", name: "Ines Roth", service: "Furnace diagnostic", channel: "Web chat", state: "COMPLETED", stage: 4, detail: "Job closed, review request sent", time: "1h ago" },
  { id: "CS-1037", name: "Wyatt Chen", service: "Drain cleaning", channel: "SMS", state: "LOST", stage: 2, detail: "Went with another provider", time: "3h ago" },
];

function StatCard({ label, value, sub, tone }) {
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

function DashboardScreen({ setView }) {
  const [filter, setFilter] = useState("ALL");
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
      <Sidebar view="dashboard" setView={setView} />
      <main className="flex-1 min-w-0 flex flex-col">
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
                {["ALL", "NEEDS_HUMAN", "QUALIFYING", "BOOKED", "LOST", "COMPLETED"].map((s) => (
                  <button key={s} onClick={() => setFilter(s)} className="px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors"
                    style={{ backgroundColor: filter === s ? "#171A21" : "transparent", color: filter === s ? "#fff" : "#6B7280" }}>
                    {s === "ALL" ? "All" : STATE_META[s].label}
                  </button>
                ))}
              </div>
              <ul>
                {filtered.map((c) => (
                  <li key={c.id} onClick={() => setSelected(c)} className="px-5 py-4 border-b border-[#F0EFE9] last:border-0 cursor-pointer transition-colors"
                    style={{ backgroundColor: selected.id === c.id ? "#FAFAF7" : "transparent" }}>
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
                  <button onClick={() => setView("conversation")} className="w-full py-2.5 rounded-lg text-sm font-medium text-white flex items-center justify-center gap-2" style={{ backgroundColor: "#171A21" }}>
                    Open conversation <ArrowUpRight size={14} />
                  </button>
                  <button className="w-full py-2.5 rounded-lg text-sm font-medium border border-[#E7E5DE]">Mark resolved</button>
                </div>
              ) : (
                <button onClick={() => setView("conversation")} className="w-full py-2.5 rounded-lg text-sm font-medium border border-[#E7E5DE] flex items-center justify-center gap-2">
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

/* ============================================================
   CONVERSATION
   ============================================================ */

const CONVERSATIONS = [
  { id: "CS-1042", name: "Marcus Webb", service: "Furnace diagnostic", state: "NEEDS_HUMAN", time: "2m ago", unread: true },
  { id: "CS-1041", name: "Priya Anand", service: "Drain cleaning", state: "BOOKED", time: "14m ago" },
  { id: "CS-1040", name: "Dana Okafor", service: "AC repair", state: "QUALIFYING", time: "22m ago" },
  { id: "CS-1039", name: "Leon Frei", service: "Water heater install", state: "QUALIFYING", time: "41m ago" },
  { id: "CS-1038", name: "Ines Roth", service: "Furnace diagnostic", state: "COMPLETED", time: "1h ago" },
];

const THREAD = [
  { from: "customer", time: "09:41", text: "Hi, my furnace is making a rattling noise, can someone come look today?" },
  { from: "ai", time: "09:41", text: "I can get that scheduled. What's the service zip code, and is anyone home this afternoon?" },
  { from: "customer", time: "09:42", text: "60601, yes I'll be home after 2pm" },
  { from: "ai", time: "09:43", text: "Great — before I lock in a window, I just need to confirm the service address matches that zip." },
  { from: "customer", time: "09:44", text: "Actually, how much does a diagnostic usually run? Want to check before I commit to a time." },
];

const AUDIT = [
  ["09:41:02", "Trigger", "Inbound web chat message received"],
  ["09:41:03", "Context", "Matched existing lead by phone"],
  ["09:41:04", "Decision", "Missing required field: service zip"],
  ["09:41:04", "Action", "Sent clarifying question"],
  ["09:44:18", "Result", "Escalated — pricing asked before address confirmed"],
];

function ConversationScreen({ setView }) {
  const [reply, setReply] = useState("");
  const [resolved, setResolved] = useState(false);

  return (
    <div className="min-h-screen w-full flex" style={{ backgroundColor: "#F7F6F2", fontFamily: "'Inter', sans-serif", color: "#171A21" }}>
      <Sidebar view="conversation" setView={setView} />
      <main className="flex-1 min-w-0 flex">
        <div className="w-72 shrink-0 border-r border-[#E7E5DE] flex flex-col">
          <div className="px-4 py-4 border-b border-[#E7E5DE]">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9AA1AC]" />
              <input placeholder="Search conversations..." className="w-full pl-8 pr-3 py-2 rounded-lg bg-white border border-[#E7E5DE] text-sm outline-none" />
            </div>
          </div>
          <ul className="flex-1 overflow-y-auto">
            {CONVERSATIONS.map((c) => (
              <li key={c.id} className="px-4 py-3.5 border-b border-[#F0EFE9] cursor-pointer" style={{ backgroundColor: c.id === "CS-1042" ? "#FAFAF7" : "transparent" }}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-semibold flex items-center gap-1.5">
                    {c.unread && <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: "#C97A1F" }} />} {c.name}
                  </span>
                  <span className="text-[11px] text-[#9AA1AC]">{c.time}</span>
                </div>
                <div className="text-xs text-[#6B7280] truncate mb-1.5">{c.service}</div>
                <StatePill state={c.state} />
              </li>
            ))}
          </ul>
        </div>

        <div className="flex-1 min-w-0 flex flex-col">
          <header className="flex items-center justify-between px-6 py-4 border-b border-[#E7E5DE]">
            <div className="flex items-center gap-3">
              <button onClick={() => setView("dashboard")} className="text-[#6B7280]"><ArrowLeft size={16} /></button>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-base font-semibold">Marcus Webb</h1>
                  <span className="text-[11px] text-[#9AA1AC]" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>CS-1042</span>
                </div>
                <p className="text-xs text-[#6B7280] mt-0.5">Furnace diagnostic · Web chat</p>
              </div>
            </div>
            <StatePill state={resolved ? "COMPLETED" : "NEEDS_HUMAN"} />
          </header>

          <div className="flex-1 overflow-y-auto px-6 py-6 flex flex-col gap-3">
            {THREAD.map((m, i) => (
              <div key={i} className={`flex flex-col ${m.from === "customer" ? "items-start" : "items-end"}`}>
                <div className={`text-sm max-w-md px-3.5 py-2.5 rounded-2xl ${m.from === "customer" ? "rounded-bl-sm" : "rounded-br-sm"}`}
                  style={m.from === "customer" ? { backgroundColor: "#F1F1EF" } : { backgroundColor: "#3A3EA6", color: "#fff" }}>
                  {m.text}
                </div>
                <span className="text-[10px] text-[#9AA1AC] mt-1 px-1">{m.from === "customer" ? "Marcus" : "Engine"} · {m.time}</span>
              </div>
            ))}

            {!resolved && (
              <div className="flex items-center gap-2 my-2 px-1">
                <div className="h-px flex-1" style={{ backgroundColor: "#E7E5DE" }} />
                <span className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full" style={{ color: "#C97A1F", backgroundColor: "#FBF0E2" }}>
                  <ShieldAlert size={11} /> Escalated to you · 09:44
                </span>
                <div className="h-px flex-1" style={{ backgroundColor: "#E7E5DE" }} />
              </div>
            )}

            {resolved && (
              <div className="flex flex-col items-end">
                <div className="text-sm max-w-md px-3.5 py-2.5 rounded-2xl rounded-br-sm text-white" style={{ backgroundColor: "#171A21" }}>
                  {reply || "A diagnostic visit runs $89, credited toward the repair if you go ahead — want me to lock in 2–4pm today?"}
                </div>
                <span className="text-[10px] text-[#9AA1AC] mt-1 px-1">You · just now</span>
              </div>
            )}
          </div>

          {!resolved ? (
            <div className="border-t border-[#E7E5DE] p-4">
              <div className="flex items-end gap-2">
                <textarea value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Reply as Acme Home Services..." rows={2}
                  className="flex-1 px-3.5 py-2.5 rounded-lg border border-[#E7E5DE] bg-white text-sm outline-none resize-none focus:ring-2 focus:ring-[#3A3EA633]" />
                <button onClick={() => setResolved(true)} className="h-10 w-10 shrink-0 rounded-lg flex items-center justify-center text-white" style={{ backgroundColor: "#171A21" }}>
                  <Send size={15} />
                </button>
              </div>
              <button onClick={() => setResolved(true)} className="mt-2 text-xs font-medium text-[#6B7280] flex items-center gap-1">
                <Check size={12} /> Mark resolved without replying
              </button>
            </div>
          ) : (
            <div className="border-t border-[#E7E5DE] p-4 flex items-center gap-2 text-sm" style={{ color: "#1E7B52" }}>
              <Check size={15} /> Reply sent — the engine will pick the conversation back up from here.
            </div>
          )}
        </div>

        <div className="w-80 shrink-0 border-l border-[#E7E5DE] p-5 hidden lg:flex flex-col gap-6">
          <div>
            <div className="text-xs font-medium text-[#9AA1AC] mb-2">Where this case is</div>
            <Stepper stage={resolved ? 4 : 2} color={resolved ? "#1E7B52" : "#C97A1F"} />
            <div className="flex justify-between mt-1.5">
              {STAGES.map((s) => <span key={s} className="text-[10px] text-[#9AA1AC]" style={{ width: 40 }}>{s}</span>)}
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs text-[#6B7280]">
            <span className="flex items-center gap-1.5"><Phone size={12} /> On file</span>
            <span className="flex items-center gap-1.5"><Mail size={12} /> On file</span>
          </div>
          <div>
            <div className="text-xs font-medium text-[#9AA1AC] mb-3" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>CS-1042 · audit trail</div>
            <div className="flex flex-col gap-2.5 text-sm">
              {AUDIT.map(([time, stage, desc]) => (
                <div key={stage} className="flex gap-3">
                  <span className="text-[#9AA1AC] shrink-0" style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 12 }}>{time}</span>
                  <span className="font-medium shrink-0 w-16">{stage}</span>
                  <span className="text-[#6B7280]">{desc}</span>
                </div>
              ))}
              {resolved && (
                <div className="flex gap-3">
                  <span className="text-[#9AA1AC] shrink-0" style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 12 }}>now</span>
                  <span className="font-medium shrink-0 w-16">Result</span>
                  <span className="text-[#6B7280]">You replied — case handed back to the engine</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

/* ============================================================
   ONBOARDING
   ============================================================ */

const OB_STEPS = [
  { key: "basics", label: "Business", icon: Building2 },
  { key: "services", label: "Services", icon: Wrench },
  { key: "area", label: "Service area", icon: MapPin },
  { key: "questions", label: "Questions", icon: MessageCircleQuestion },
  { key: "escalation", label: "Escalation", icon: ShieldAlert },
  { key: "review", label: "Review", icon: Sparkles },
];

function ProgressRail({ current }) {
  return (
    <div className="flex flex-col gap-0.5">
      {OB_STEPS.map((s, i) => {
        const done = i < current;
        const active = i === current;
        const Icon = s.icon;
        return (
          <div key={s.key} className="flex items-start gap-3">
            <div className="flex flex-col items-center">
              <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 transition-colors"
                style={{ backgroundColor: done ? "#1E7B52" : active ? "#171A21" : "#F1F1EF", color: done || active ? "#fff" : "#9AA1AC" }}>
                {done ? <Check size={14} /> : <Icon size={14} />}
              </div>
              {i < OB_STEPS.length - 1 && <div className="w-px flex-1 min-h-[22px]" style={{ backgroundColor: done ? "#1E7B52" : "#E7E5DE" }} />}
            </div>
            <div className="pt-1.5 pb-4">
              <div className="text-sm" style={{ color: active || done ? "#171A21" : "#9AA1AC", fontWeight: active ? 600 : 500 }}>{s.label}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Field({ label, hint, children }) {
  return (
    <div className="mb-5">
      <label className="block text-sm font-medium mb-1.5">{label}</label>
      {hint && <p className="text-xs text-[#9AA1AC] mb-2">{hint}</p>}
      {children}
    </div>
  );
}

const inputCls = "w-full px-3.5 py-2.5 rounded-lg border border-[#E7E5DE] bg-white text-sm outline-none focus:ring-2 focus:ring-[#3A3EA633] focus:border-[#3A3EA6] transition-shadow";

function ToneOption({ label, desc, active, onClick }) {
  return (
    <button onClick={onClick} className="text-left px-4 py-3 rounded-xl border transition-colors" style={{ borderColor: active ? "#3A3EA6" : "#E7E5DE", backgroundColor: active ? "#EEEEF9" : "#fff" }}>
      <div className="text-sm font-medium mb-0.5">{label}</div>
      <div className="text-xs text-[#6B7280]">{desc}</div>
    </button>
  );
}

function OnboardingScreen({ setView }) {
  const [step, setStep] = useState(0);
  const [business, setBusiness] = useState({ name: "", industry: "Home services", tone: "Friendly & direct" });
  const [services, setServices] = useState(["Furnace diagnostic", "AC repair", "Drain cleaning"]);
  const [newService, setNewService] = useState("");
  const [radius, setRadius] = useState(25);
  const [zips, setZips] = useState("60601, 60602, 60603");
  const [questions, setQuestions] = useState({ "Furnace diagnostic": ["Unit age?", "Making unusual noise or smell?"] });
  const [escalation, setEscalation] = useState({ outsideArea: true, priceObjection: true, angryTone: true });
  const [launched, setLaunched] = useState(false);

  const next = () => setStep((s) => Math.min(s + 1, OB_STEPS.length - 1));
  const back = () => setStep((s) => Math.max(s - 1, 0));
  const addService = () => {
    if (newService.trim()) { setServices([...services, newService.trim()]); setNewService(""); }
  };

  return (
    <div style={{ backgroundColor: "#F7F6F2", fontFamily: "'Inter', sans-serif", color: "#171A21" }} className="min-h-screen w-full">
      <header className="border-b border-[#E7E5DE] bg-white">
        <div className="max-w-5xl mx-auto px-6 h-16 flex items-center justify-between">
          <button onClick={() => setView("landing")} className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg flex items-center justify-center text-white text-xs font-bold" style={{ backgroundColor: "#3A3EA6", fontFamily: "'Space Grotesk', sans-serif" }}>A</div>
            <span className="font-semibold text-sm" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>Setting up your Business DNA</span>
          </button>
          <span className="text-xs text-[#9AA1AC]" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>Step {step + 1} / {OB_STEPS.length}</span>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-6 py-10 md:py-14 grid md:grid-cols-[200px_1fr] gap-10">
        <div className="hidden md:block"><ProgressRail current={step} /></div>

        <div className="bg-white rounded-2xl border border-[#E7E5DE] p-6 md:p-8 min-h-[480px] flex flex-col">
          {!launched ? (
            <>
              <div className="flex-1 dna-fade" key={step}>
                {step === 0 && (
                  <>
                    <h2 className="text-2xl mb-1.5" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>Tell us about your business</h2>
                    <p className="text-sm text-[#6B7280] mb-7">This shapes how your engine talks to every customer.</p>
                    <Field label="Business name">
                      <input className={inputCls} placeholder="Acme Home Services" value={business.name} onChange={(e) => setBusiness({ ...business, name: e.target.value })} />
                    </Field>
                    <Field label="Industry">
                      <select className={inputCls} value={business.industry} onChange={(e) => setBusiness({ ...business, industry: e.target.value })}>
                        <option>Home services</option><option>Auto repair</option><option>Health & wellness</option><option>Professional services</option>
                      </select>
                    </Field>
                    <Field label="How should it sound to customers?">
                      <div className="grid sm:grid-cols-3 gap-2.5">
                        {[["Friendly & direct", "Warm, no filler"], ["Formal & precise", "Professional tone"], ["Casual & brief", "Short, plain texts"]].map(([label, desc]) => (
                          <ToneOption key={label} label={label} desc={desc} active={business.tone === label} onClick={() => setBusiness({ ...business, tone: label })} />
                        ))}
                      </div>
                    </Field>
                  </>
                )}

                {step === 1 && (
                  <>
                    <h2 className="text-2xl mb-1.5" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>What do you offer?</h2>
                    <p className="text-sm text-[#6B7280] mb-7">This is what it'll book, quote, and answer questions about.</p>
                    <div className="flex flex-wrap gap-2 mb-4">
                      {services.map((s) => (
                        <span key={s} className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm bg-[#F1F1EF] border border-[#E7E5DE]">
                          {s} <X size={12} className="cursor-pointer text-[#9AA1AC]" onClick={() => setServices(services.filter((x) => x !== s))} />
                        </span>
                      ))}
                    </div>
                    <div className="flex gap-2">
                      <input className={inputCls} placeholder="Add a service" value={newService} onChange={(e) => setNewService(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addService()} />
                      <button onClick={addService} className="px-4 rounded-lg text-white text-sm font-medium flex items-center gap-1.5 shrink-0" style={{ backgroundColor: "#171A21" }}>
                        <Plus size={14} /> Add
                      </button>
                    </div>
                  </>
                )}

                {step === 2 && (
                  <>
                    <h2 className="text-2xl mb-1.5" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>Where do you work?</h2>
                    <p className="text-sm text-[#6B7280] mb-7">Leads outside this area escalate to you instead of getting booked automatically.</p>
                    <Field label="Service radius" hint={`${radius} miles from your base zip code`}>
                      <input type="range" min="5" max="60" value={radius} onChange={(e) => setRadius(e.target.value)} className="w-full accent-[#3A3EA6]" />
                    </Field>
                    <Field label="Known service zip codes" hint="Comma-separated — the engine matches against these first">
                      <textarea className={inputCls} rows={3} value={zips} onChange={(e) => setZips(e.target.value)} />
                    </Field>
                  </>
                )}

                {step === 3 && (
                  <>
                    <h2 className="text-2xl mb-1.5" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>What does it need to ask?</h2>
                    <p className="text-sm text-[#6B7280] mb-7">Per service, the questions your engine confirms before booking.</p>
                    {services.map((svc) => (
                      <div key={svc} className="mb-5 pb-5 border-b border-[#F0EFE9] last:border-0">
                        <div className="text-sm font-semibold mb-2.5">{svc}</div>
                        <div className="flex flex-col gap-2">
                          {(questions[svc] || ["What's the issue you're experiencing?"]).map((q, i) => (
                            <div key={i} className="flex items-center gap-2">
                              <span className="text-xs text-[#9AA1AC] w-5 shrink-0" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>{i + 1}</span>
                              <input className={inputCls} defaultValue={q} />
                            </div>
                          ))}
                          <button className="text-xs font-medium text-[#3A3EA6] flex items-center gap-1 mt-0.5 ml-7"
                            onClick={() => setQuestions({ ...questions, [svc]: [...(questions[svc] || []), ""] })}>
                            <Plus size={12} /> Add question
                          </button>
                        </div>
                      </div>
                    ))}
                  </>
                )}

                {step === 4 && (
                  <>
                    <h2 className="text-2xl mb-1.5" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>When should it hand off to you?</h2>
                    <p className="text-sm text-[#6B7280] mb-7">The engine never guesses past these lines — it stops and asks.</p>
                    <div className="flex flex-col gap-3">
                      {[
                        ["outsideArea", "Lead is outside your service area", "Never auto-books a job it can't confirm you can reach."],
                        ["priceObjection", "Customer pushes back on price", "Pricing conversations route to you by default."],
                        ["angryTone", "Message reads as frustrated or urgent", "Tone signals that call for a person, not a script."],
                      ].map(([key, title, desc]) => (
                        <label key={key} className="flex items-start gap-3 p-4 rounded-xl border cursor-pointer"
                          style={{ borderColor: escalation[key] ? "#3A3EA6" : "#E7E5DE", backgroundColor: escalation[key] ? "#EEEEF9" : "#fff" }}>
                          <input type="checkbox" checked={escalation[key]} onChange={() => setEscalation({ ...escalation, [key]: !escalation[key] })} className="mt-0.5 accent-[#3A3EA6]" />
                          <div>
                            <div className="text-sm font-medium">{title}</div>
                            <div className="text-xs text-[#6B7280] mt-0.5">{desc}</div>
                          </div>
                        </label>
                      ))}
                    </div>
                  </>
                )}

                {step === 5 && (
                  <>
                    <h2 className="text-2xl mb-1.5" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>Ready to go live</h2>
                    <p className="text-sm text-[#6B7280] mb-7">Here's the Business DNA your engine will run on.</p>
                    <div className="rounded-xl bg-[#F7F6F2] border border-[#E7E5DE] p-5 flex flex-col gap-4 text-sm">
                      <div className="flex justify-between"><span className="text-[#6B7280]">Business</span><span className="font-medium">{business.name || "Untitled business"} · {business.industry}</span></div>
                      <div className="flex justify-between"><span className="text-[#6B7280]">Voice</span><span className="font-medium">{business.tone}</span></div>
                      <div className="flex justify-between"><span className="text-[#6B7280]">Services</span><span className="font-medium text-right">{services.join(", ")}</span></div>
                      <div className="flex justify-between"><span className="text-[#6B7280]">Service radius</span><span className="font-medium">{radius} miles</span></div>
                      <div className="flex justify-between"><span className="text-[#6B7280]">Escalation rules</span><span className="font-medium">{Object.values(escalation).filter(Boolean).length} active</span></div>
                    </div>
                    <div className="flex items-center gap-2 mt-5 text-xs" style={{ color: "#1E7B52" }}>
                      <Check size={14} /> This won't change how existing conversations behave — only new ones.
                    </div>
                  </>
                )}
              </div>

              <div className="flex items-center justify-between pt-6 mt-6 border-t border-[#F0EFE9]">
                <button onClick={back} disabled={step === 0} className="text-sm font-medium px-4 py-2.5 rounded-lg flex items-center gap-1.5 disabled:opacity-0" style={{ color: "#6B7280" }}>
                  <ArrowLeft size={14} /> Back
                </button>
                {step < OB_STEPS.length - 1 ? (
                  <button onClick={next} className="text-sm font-medium text-white px-5 py-2.5 rounded-lg flex items-center gap-1.5" style={{ backgroundColor: "#171A21" }}>
                    Continue <ArrowRight size={14} />
                  </button>
                ) : (
                  <button onClick={() => setLaunched(true)} className="text-sm font-medium text-white px-5 py-2.5 rounded-lg flex items-center gap-1.5" style={{ backgroundColor: "#1E7B52" }}>
                    Launch engine <Sparkles size={14} />
                  </button>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-center dna-fade">
              <div className="w-12 h-12 rounded-full flex items-center justify-center mb-5" style={{ backgroundColor: "#E9F5EF" }}>
                <Check size={22} color="#1E7B52" />
              </div>
              <h2 className="text-2xl mb-2" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>
                {business.name || "Your business"} is live.
              </h2>
              <p className="text-sm text-[#6B7280] mb-7 max-w-sm">It's answering new leads right now, using exactly what you just set up.</p>
              <button onClick={() => setView("dashboard")} className="text-sm font-medium text-white px-5 py-2.5 rounded-lg flex items-center gap-1.5" style={{ backgroundColor: "#171A21" }}>
                Go to dashboard <ArrowRight size={14} />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   SETTINGS
   ============================================================ */

const SETTINGS_TABS = [
  { key: "business", label: "Business" },
  { key: "services", label: "Services" },
  { key: "area", label: "Service area" },
  { key: "questions", label: "Questions" },
  { key: "escalation", label: "Escalation" },
];

const SETTINGS_INITIAL = {
  name: "Acme Home Services",
  industry: "Home services",
  tone: "Friendly & direct",
  services: ["Furnace diagnostic", "AC repair", "Drain cleaning"],
  radius: 25,
  zips: "60601, 60602, 60603",
  questions: {
    "Furnace diagnostic": ["Unit age?", "Making unusual noise or smell?"],
    "AC repair": ["Is the unit still running, just poorly, or fully off?"],
    "Drain cleaning": ["Which drain — kitchen, bathroom, or main line?"],
  },
  escalation: { outsideArea: true, priceObjection: true, angryTone: true },
};

function SettingsScreen({ setView }) {
  const [tab, setTab] = useState("business");
  const [state, setState] = useState(SETTINGS_INITIAL);
  const [newService, setNewService] = useState("");
  const [savedAt, setSavedAt] = useState("2 days ago");
  const dirty = useMemo(() => JSON.stringify(state) !== JSON.stringify(SETTINGS_INITIAL), [state]);

  const addService = () => {
    const v = newService.trim();
    if (v && !state.services.includes(v)) { setState({ ...state, services: [...state.services, v] }); setNewService(""); }
  };
  const removeService = (s) => setState({ ...state, services: state.services.filter((x) => x !== s) });
  const save = () => setSavedAt("just now");
  const discard = () => setState(SETTINGS_INITIAL);

  return (
    <div className="min-h-screen w-full flex" style={{ backgroundColor: "#F7F6F2", fontFamily: "'Inter', sans-serif", color: "#171A21" }}>
      <Sidebar view="settings" setView={setView} />
      <main className="flex-1 min-w-0 flex flex-col">
        <header className="flex items-center justify-between px-6 md:px-8 py-4 border-b border-[#E7E5DE]">
          <div>
            <h1 className="text-xl" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>Business DNA</h1>
            <p className="text-sm text-[#6B7280] mt-0.5" style={{ fontFamily: dirty ? "'Inter', sans-serif" : "'IBM Plex Mono', monospace" }}>
              {dirty ? "Unsaved changes" : `Last updated ${savedAt}`}
            </p>
          </div>
          {!dirty && (
            <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full" style={{ color: "#1E7B52", backgroundColor: "#E9F5EF" }}>
              <Check size={12} /> Live
            </span>
          )}
        </header>

        <div className="max-w-3xl px-6 md:px-8 py-8 w-full">
          <div className="flex items-center gap-1 mb-8 border-b border-[#E7E5DE] overflow-x-auto">
            {SETTINGS_TABS.map((t) => (
              <button key={t.key} onClick={() => setTab(t.key)} className="px-3.5 py-2.5 text-sm whitespace-nowrap relative -mb-px"
                style={{ color: tab === t.key ? "#171A21" : "#9AA1AC", fontWeight: tab === t.key ? 600 : 500 }}>
                {t.label}
                {tab === t.key && <span className="absolute left-0 right-0 -bottom-px h-0.5" style={{ backgroundColor: "#171A21" }} />}
              </button>
            ))}
          </div>

          {tab === "business" && (
            <div>
              <Field label="Business name"><input className={inputCls} value={state.name} onChange={(e) => setState({ ...state, name: e.target.value })} /></Field>
              <Field label="Industry">
                <select className={inputCls} value={state.industry} onChange={(e) => setState({ ...state, industry: e.target.value })}>
                  <option>Home services</option><option>Auto repair</option><option>Health & wellness</option><option>Professional services</option>
                </select>
              </Field>
              <Field label="How should it sound to customers?">
                <div className="grid sm:grid-cols-3 gap-2.5">
                  {[["Friendly & direct", "Warm, no filler"], ["Formal & precise", "Professional tone"], ["Casual & brief", "Short, plain texts"]].map(([label, desc]) => (
                    <ToneOption key={label} label={label} desc={desc} active={state.tone === label} onClick={() => setState({ ...state, tone: label })} />
                  ))}
                </div>
              </Field>
            </div>
          )}

          {tab === "services" && (
            <Field label="What you offer" hint="These are what it books, quotes, and answers questions about.">
              <div className="flex flex-wrap gap-2 mb-3">
                {state.services.map((s) => (
                  <span key={s} className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm bg-[#F1F1EF] border border-[#E7E5DE]">
                    {s} <X size={12} className="cursor-pointer text-[#9AA1AC]" onClick={() => removeService(s)} />
                  </span>
                ))}
              </div>
              <div className="flex gap-2">
                <input className={inputCls} placeholder="Add a service" value={newService} onChange={(e) => setNewService(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addService()} />
                <button onClick={addService} className="px-4 rounded-lg text-white text-sm font-medium flex items-center gap-1.5 shrink-0" style={{ backgroundColor: "#171A21" }}>
                  <Plus size={14} /> Add
                </button>
              </div>
            </Field>
          )}

          {tab === "area" && (
            <div>
              <Field label="Service radius" hint={`${state.radius} miles from your base zip code`}>
                <input type="range" min="5" max="60" value={state.radius} onChange={(e) => setState({ ...state, radius: Number(e.target.value) })} className="w-full accent-[#3A3EA6]" />
              </Field>
              <Field label="Known service zip codes" hint="Comma-separated — the engine matches against these first">
                <textarea className={inputCls} rows={3} value={state.zips} onChange={(e) => setState({ ...state, zips: e.target.value })} />
              </Field>
            </div>
          )}

          {tab === "questions" && (
            <div>
              <p className="text-sm text-[#6B7280] mb-6">Per service, the questions your engine confirms before booking.</p>
              {state.services.map((svc) => (
                <div key={svc} className="mb-5 pb-5 border-b border-[#F0EFE9] last:border-0">
                  <div className="text-sm font-semibold mb-2.5">{svc}</div>
                  <div className="flex flex-col gap-2">
                    {(state.questions[svc] || ["What's the issue you're experiencing?"]).map((q, i) => (
                      <div key={i} className="flex items-center gap-2">
                        <span className="text-xs text-[#9AA1AC] w-5 shrink-0" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>{i + 1}</span>
                        <input className={inputCls} value={q} onChange={(e) => {
                          const qs = [...(state.questions[svc] || [])]; qs[i] = e.target.value;
                          setState({ ...state, questions: { ...state.questions, [svc]: qs } });
                        }} />
                      </div>
                    ))}
                    <button className="text-xs font-medium text-[#3A3EA6] flex items-center gap-1 mt-0.5 ml-7"
                      onClick={() => setState({ ...state, questions: { ...state.questions, [svc]: [...(state.questions[svc] || []), ""] } })}>
                      <Plus size={12} /> Add question
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {tab === "escalation" && (
            <div className="flex flex-col gap-3">
              <p className="text-sm text-[#6B7280] mb-1">The engine never guesses past these lines — it stops and asks.</p>
              {[
                ["outsideArea", "Lead is outside your service area", "Never auto-books a job it can't confirm you can reach."],
                ["priceObjection", "Customer pushes back on price", "Pricing conversations route to you by default."],
                ["angryTone", "Message reads as frustrated or urgent", "Tone signals that call for a person, not a script."],
              ].map(([key, title, desc]) => (
                <label key={key} className="flex items-start gap-3 p-4 rounded-xl border cursor-pointer"
                  style={{ borderColor: state.escalation[key] ? "#3A3EA6" : "#E7E5DE", backgroundColor: state.escalation[key] ? "#EEEEF9" : "#fff" }}>
                  <input type="checkbox" checked={state.escalation[key]} onChange={() => setState({ ...state, escalation: { ...state.escalation, [key]: !state.escalation[key] } })} className="mt-0.5 accent-[#3A3EA6]" />
                  <div>
                    <div className="text-sm font-medium">{title}</div>
                    <div className="text-xs text-[#6B7280] mt-0.5">{desc}</div>
                  </div>
                </label>
              ))}
            </div>
          )}
        </div>

        {dirty && (
          <div className="sticky bottom-0 border-t border-[#E7E5DE] bg-white px-6 md:px-8 py-4 flex items-center justify-between">
            <span className="text-xs text-[#6B7280]">This won't change how existing conversations behave — only new ones.</span>
            <div className="flex items-center gap-2">
              <button onClick={discard} className="text-sm font-medium px-4 py-2.5 rounded-lg border border-[#E7E5DE] flex items-center gap-1.5"><RotateCcw size={13} /> Discard</button>
              <button onClick={save} className="text-sm font-medium text-white px-5 py-2.5 rounded-lg" style={{ backgroundColor: "#171A21" }}>Save changes</button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

/* ============================================================
   APP SHELL — five screens, one state machine of its own
   ============================================================ */

const VIEWS = [
  { key: "landing", label: "Landing" },
  { key: "onboarding", label: "Onboarding" },
  { key: "dashboard", label: "Dashboard" },
  { key: "conversation", label: "Conversation" },
  { key: "settings", label: "Business DNA" },
];

export default function AtelierPrototype() {
  const [view, setView] = useState("landing");

  const screens = {
    landing: <LandingScreen setView={setView} />,
    onboarding: <OnboardingScreen setView={setView} />,
    dashboard: <DashboardScreen setView={setView} />,
    conversation: <ConversationScreen setView={setView} />,
    settings: <SettingsScreen setView={setView} />,
  };

  return (
    <div className="relative">
      <GlobalStyle />
      {screens[view]}

      {/* Demo switcher — not part of the product UI, just for walking through the prototype live */}
      <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-1 px-1.5 py-1.5 rounded-full shadow-lg"
        style={{ backgroundColor: "#171A21" }}>
        {VIEWS.map((v) => (
          <button
            key={v.key}
            onClick={() => setView(v.key)}
            className="px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors"
            style={{
              backgroundColor: view === v.key ? "#3A3EA6" : "transparent",
              color: view === v.key ? "#fff" : "#9AA1AC",
              fontFamily: "'Inter', sans-serif",
            }}
          >
            {v.label}
          </button>
        ))}
      </div>
    </div>
  );
}
