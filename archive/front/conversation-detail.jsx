import React, { useState } from "react";
import {
  Search, Bell, LayoutGrid, Users, MessageSquare, Workflow, Settings,
  Phone, Mail, ArrowLeft, Send, Check, ShieldAlert,
} from "lucide-react";

/* Same design system as landing + dashboard + onboarding:
   Background #F7F6F2 · Surface #FFFFFF · Ink #171A21 · Muted #6B7280
   Line #E7E5DE · Accent indigo #3A3EA6 · Amber #C97A1F · Green #1E7B52 · Red #B4483A
   Display: Space Grotesk · Body: Inter · Utility: IBM Plex Mono */

const STAGES = ["Trigger", "Context", "Decision", "Action", "Result"];

const CONVERSATIONS = [
  { id: "CS-1042", name: "Marcus Webb", service: "Furnace diagnostic", state: "NEEDS_HUMAN", time: "2m ago", unread: true },
  { id: "CS-1041", name: "Priya Anand", service: "Drain cleaning", state: "BOOKED", time: "14m ago" },
  { id: "CS-1040", name: "Dana Okafor", service: "AC repair", state: "QUALIFYING", time: "22m ago" },
  { id: "CS-1039", name: "Leon Frei", service: "Water heater install", state: "QUALIFYING", time: "41m ago" },
  { id: "CS-1038", name: "Ines Roth", service: "Furnace diagnostic", state: "COMPLETED", time: "1h ago" },
];

const STATE_META = {
  NEW: { label: "New", color: "#6B7280", bg: "#F1F1EF" },
  QUALIFYING: { label: "Qualifying", color: "#3A3EA6", bg: "#EEEEF9" },
  NEEDS_HUMAN: { label: "Needs you", color: "#C97A1F", bg: "#FBF0E2" },
  BOOKED: { label: "Booked", color: "#1E7B52", bg: "#E9F5EF" },
  LOST: { label: "Lost", color: "#B4483A", bg: "#FBEBE9" },
  COMPLETED: { label: "Completed", color: "#171A21", bg: "#F1F1EF" },
};

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

function Stepper({ stage, color }) {
  return (
    <div className="flex items-center gap-1.5">
      {STAGES.map((label, i) => (
        <div key={label} className="flex items-center gap-1.5">
          <div
            className="w-2 h-2 rounded-full"
            style={{
              backgroundColor: i <= stage ? color : "#DEDBD2",
              boxShadow: i === stage ? `0 0 0 3px ${color}22` : "none",
            }}
            title={label}
          />
          {i < STAGES.length - 1 && (
            <div className="h-px w-4" style={{ backgroundColor: i < stage ? color : "#DEDBD2" }} />
          )}
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

function NavItem({ icon: Icon, label, active }) {
  return (
    <button
      className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors"
      style={{ color: active ? "#171A21" : "#6B7280", backgroundColor: active ? "#EEEEF9" : "transparent", fontWeight: active ? 600 : 500 }}
    >
      <Icon size={17} strokeWidth={2} />
      {label}
    </button>
  );
}

export default function ConversationDetail() {
  const [reply, setReply] = useState("");
  const [resolved, setResolved] = useState(false);

  return (
    <div className="min-h-screen w-full flex" style={{ backgroundColor: "#F7F6F2", fontFamily: "'Inter', sans-serif", color: "#171A21" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
        * { box-sizing: border-box; }
      `}</style>

      {/* Sidebar — identical to the dashboard */}
      <aside className="w-60 shrink-0 border-r border-[#E7E5DE] px-4 py-5 hidden md:flex md:flex-col justify-between">
        <div>
          <div className="flex items-center gap-2 px-2 mb-8">
            <div className="w-7 h-7 rounded-lg flex items-center justify-center text-white text-xs font-bold" style={{ backgroundColor: "#3A3EA6", fontFamily: "'Space Grotesk', sans-serif" }}>A</div>
            <div>
              <div className="text-sm font-semibold leading-tight">Acme Home Services</div>
              <div className="text-[11px] text-[#6B7280] leading-tight">Business DNA v3</div>
            </div>
          </div>
          <nav className="flex flex-col gap-1">
            <NavItem icon={LayoutGrid} label="Overview" />
            <NavItem icon={Users} label="Leads & cases" />
            <NavItem icon={MessageSquare} label="Conversations" active />
            <NavItem icon={Workflow} label="Business DNA" />
            <NavItem icon={Settings} label="Settings" />
          </nav>
        </div>
        <div className="px-2 text-[11px] text-[#9AA1AC] leading-relaxed">
          Every step your engine takes — logged, reversible, never silent.
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 min-w-0 flex">
        {/* Conversation list */}
        <div className="w-72 shrink-0 border-r border-[#E7E5DE] flex flex-col">
          <div className="px-4 py-4 border-b border-[#E7E5DE]">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9AA1AC]" />
              <input placeholder="Search conversations..." className="w-full pl-8 pr-3 py-2 rounded-lg bg-white border border-[#E7E5DE] text-sm outline-none" />
            </div>
          </div>
          <ul className="flex-1 overflow-y-auto">
            {CONVERSATIONS.map((c) => (
              <li
                key={c.id}
                className="px-4 py-3.5 border-b border-[#F0EFE9] cursor-pointer"
                style={{ backgroundColor: c.id === "CS-1042" ? "#FAFAF7" : "transparent" }}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-semibold flex items-center gap-1.5">
                    {c.unread && <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: "#C97A1F" }} />}
                    {c.name}
                  </span>
                  <span className="text-[11px] text-[#9AA1AC]">{c.time}</span>
                </div>
                <div className="text-xs text-[#6B7280] truncate mb-1.5">{c.service}</div>
                <StatePill state={c.state} />
              </li>
            ))}
          </ul>
        </div>

        {/* Thread */}
        <div className="flex-1 min-w-0 flex flex-col">
          <header className="flex items-center justify-between px-6 py-4 border-b border-[#E7E5DE]">
            <div className="flex items-center gap-3">
              <button className="md:hidden text-[#6B7280]"><ArrowLeft size={16} /></button>
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
                <div
                  className={`text-sm max-w-md px-3.5 py-2.5 rounded-2xl ${m.from === "customer" ? "rounded-bl-sm" : "rounded-br-sm"}`}
                  style={m.from === "customer" ? { backgroundColor: "#F1F1EF" } : { backgroundColor: "#3A3EA6", color: "#fff" }}
                >
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

          {/* Composer */}
          {!resolved ? (
            <div className="border-t border-[#E7E5DE] p-4">
              <div className="flex items-end gap-2">
                <textarea
                  value={reply}
                  onChange={(e) => setReply(e.target.value)}
                  placeholder="Reply as Acme Home Services..."
                  rows={2}
                  className="flex-1 px-3.5 py-2.5 rounded-lg border border-[#E7E5DE] bg-white text-sm outline-none resize-none focus:ring-2 focus:ring-[#3A3EA633]"
                />
                <button
                  onClick={() => setResolved(true)}
                  className="h-10 w-10 shrink-0 rounded-lg flex items-center justify-center text-white"
                  style={{ backgroundColor: "#171A21" }}
                >
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

        {/* Metadata panel */}
        <div className="w-80 shrink-0 border-l border-[#E7E5DE] p-5 hidden lg:flex flex-col gap-6">
          <div>
            <div className="text-xs font-medium text-[#9AA1AC] mb-2">Where this case is</div>
            <Stepper stage={resolved ? 4 : 2} color={resolved ? "#1E7B52" : "#C97A1F"} />
            <div className="flex justify-between mt-1.5">
              {STAGES.map((s) => (
                <span key={s} className="text-[10px] text-[#9AA1AC]" style={{ width: 40 }}>{s}</span>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-4 text-xs text-[#6B7280]">
            <span className="flex items-center gap-1.5"><Phone size={12} /> On file</span>
            <span className="flex items-center gap-1.5"><Mail size={12} /> On file</span>
          </div>

          <div>
            <div className="text-xs font-medium text-[#9AA1AC] mb-3" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>
              CS-1042 · audit trail
            </div>
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
