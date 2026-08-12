import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Search, Send, ShieldAlert, Check, Phone, Mail } from "lucide-react";
import { Sidebar } from "../components/Sidebar";
import { STAGES, StatePill, Stepper, PreviewBanner } from "../components/Shared";

/** Preview data — see Dashboard.tsx for why this isn't wired to a real API yet. */
const CONVERSATIONS = [
  { id: "CS-1042", name: "Marcus Webb", service: "Furnace diagnostic", state: "NEEDS_HUMAN" as const, time: "2m ago", unread: true },
  { id: "CS-1041", name: "Priya Anand", service: "Drain cleaning", state: "BOOKED" as const, time: "14m ago" },
  { id: "CS-1040", name: "Dana Okafor", service: "AC repair", state: "QUALIFYING" as const, time: "22m ago" },
  { id: "CS-1039", name: "Leon Frei", service: "Water heater install", state: "QUALIFYING" as const, time: "41m ago" },
  { id: "CS-1038", name: "Ines Roth", service: "Furnace diagnostic", state: "COMPLETED" as const, time: "1h ago" },
];

const THREAD = [
  { from: "customer", time: "09:41", text: "Hi, my furnace is making a rattling noise, can someone come look today?" },
  { from: "ai", time: "09:41", text: "I can get that scheduled. What's the service zip code, and is anyone home this afternoon?" },
  { from: "customer", time: "09:42", text: "60601, yes I'll be home after 2pm" },
  { from: "ai", time: "09:43", text: "Great — before I lock in a window, I just need to confirm the service address matches that zip." },
  { from: "customer", time: "09:44", text: "Actually, how much does a diagnostic usually run? Want to check before I commit to a time." },
];

const AUDIT: [string, string, string][] = [
  ["09:41:02", "Trigger", "Inbound web chat message received"],
  ["09:41:03", "Context", "Matched existing lead by phone"],
  ["09:41:04", "Decision", "Missing required field: service zip"],
  ["09:41:04", "Action", "Sent clarifying question"],
  ["09:44:18", "Result", "Escalated — pricing asked before address confirmed"],
];

export default function Conversation() {
  const navigate = useNavigate();
  const [reply, setReply] = useState("");
  const [resolved, setResolved] = useState(false);

  return (
    <div className="min-h-screen w-full flex" style={{ backgroundColor: "#F7F6F2", fontFamily: "'Inter', sans-serif", color: "#171A21" }}>
      <Sidebar />
      <main className="flex-1 min-w-0 flex flex-col">
        <PreviewBanner text="Preview data — replying here doesn't send anything yet; the conversation API ships next." />
        <div className="flex-1 min-w-0 flex">
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
                <button onClick={() => navigate("/app")} className="text-[#6B7280]"><ArrowLeft size={16} /></button>
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

            {!resolved ? (
              <div className="border-t border-[#E7E5DE] p-4">
                <div className="flex items-end gap-2">
                  <textarea
                    value={reply}
                    onChange={(e) => setReply(e.target.value)}
                    placeholder="Reply as your business..."
                    rows={2}
                    className="flex-1 px-3.5 py-2.5 rounded-lg border border-[#E7E5DE] bg-white text-sm outline-none resize-none focus:ring-2 focus:ring-[#3A3EA633]"
                  />
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
        </div>
      </main>
    </div>
  );
}
