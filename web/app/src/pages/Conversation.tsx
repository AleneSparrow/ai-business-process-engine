import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, Search, Send, Phone, Mail, Loader2 } from "lucide-react";
import { Sidebar } from "../components/Sidebar";
import { STAGES, StatePill, Stepper, mapProcessState, describeEvent, formatRelativeTime } from "../components/Shared";
import { useAuth, describeError } from "../auth/AuthContext";
import {
  api,
  type DashboardConversationSummary,
  type DashboardConversationDetail,
  type DashboardCaseDetail,
} from "../api/client";

export default function Conversation() {
  const navigate = useNavigate();
  const { token, user } = useAuth();
  const [searchParams] = useSearchParams();
  const requestedCaseId = searchParams.get("case");

  const [conversations, setConversations] = useState<DashboardConversationSummary[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DashboardConversationDetail | null>(null);
  const [caseDetail, setCaseDetail] = useState<DashboardCaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reply, setReply] = useState("");

  useEffect(() => {
    let cancelled = false;
    if (!token || !user?.business_id) return;
    api
      .listConversations(token, user.business_id)
      .then((res) => {
        if (cancelled) return;
        setConversations(res.conversations);
        const byCase = requestedCaseId ? res.conversations.find((c) => c.case_id === requestedCaseId) : undefined;
        setSelectedId((prev) => prev ?? byCase?.conversation_id ?? res.conversations[0]?.conversation_id ?? null);
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, user?.business_id]);

  useEffect(() => {
    let cancelled = false;
    setDetail(null);
    setCaseDetail(null);
    if (!token || !user?.business_id || !selectedId) return;
    const businessId = user.business_id;
    api
      .getConversation(token, businessId, selectedId)
      .then((res) => {
        if (cancelled) return;
        setDetail(res);
        if (res.conversation.case_id) {
          return api
            .getCase(token, businessId, res.conversation.case_id)
            .then((c) => {
              if (!cancelled) setCaseDetail(c);
            })
            .catch(() => undefined);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err));
      });
    return () => {
      cancelled = true;
    };
  }, [token, user?.business_id, selectedId]);

  const stateInfo = useMemo(() => (caseDetail ? mapProcessState(caseDetail.current_state) : null), [caseDetail]);

  return (
    <div className="min-h-screen w-full flex" style={{ backgroundColor: "#F7F6F2", fontFamily: "'Inter', sans-serif", color: "#171A21" }}>
      <Sidebar />
      <main className="flex-1 min-w-0 flex flex-col">
        <div className="flex-1 min-w-0 flex">
          <div className="w-72 shrink-0 border-r border-[#E7E5DE] flex flex-col">
            <div className="px-4 py-4 border-b border-[#E7E5DE]">
              <div className="relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9AA1AC]" />
                <input placeholder="Search conversations..." className="w-full pl-8 pr-3 py-2 rounded-lg bg-white border border-[#E7E5DE] text-sm outline-none" />
              </div>
            </div>
            {error && (
              <div className="mx-4 mt-3 px-3 py-2 rounded-lg text-xs" style={{ backgroundColor: "#FBEBE9", color: "#8A3225" }}>
                {error}
              </div>
            )}
            {conversations === null ? (
              !error && (
                <div className="flex items-center gap-2 text-sm text-[#6B7280] py-8 justify-center">
                  <Loader2 size={16} className="animate-spin" /> Loading…
                </div>
              )
            ) : conversations.length === 0 ? (
              <div className="px-4 py-8 text-sm text-[#6B7280] text-center">No conversations yet.</div>
            ) : (
              <ul className="flex-1 overflow-y-auto">
                {conversations.map((c) => {
                  const meta = mapProcessState(c.case_state ?? "NEW_LEAD");
                  return (
                    <li
                      key={c.conversation_id}
                      onClick={() => setSelectedId(c.conversation_id)}
                      className="px-4 py-3.5 border-b border-[#F0EFE9] cursor-pointer"
                      style={{ backgroundColor: c.conversation_id === selectedId ? "#FAFAF7" : "transparent" }}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-semibold">{c.lead_name || "Unnamed lead"}</span>
                        <span className="text-[11px] text-[#9AA1AC]">{formatRelativeTime(c.last_activity_at)}</span>
                      </div>
                      <div className="text-xs text-[#6B7280] truncate mb-1.5">{c.channel} · {c.status.replaceAll("_", " ")}</div>
                      {c.case_state && <StatePill state={meta.caseState} />}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <div className="flex-1 min-w-0 flex flex-col">
            {!selectedId ? (
              <div className="flex-1 flex items-center justify-center text-sm text-[#6B7280]">
                {conversations === null ? "Loading…" : "Select a conversation"}
              </div>
            ) : !detail ? (
              <div className="flex-1 flex items-center justify-center text-sm text-[#6B7280]">
                <Loader2 size={16} className="animate-spin mr-2" /> Loading conversation…
              </div>
            ) : (
              <>
                <header className="flex items-center justify-between px-6 py-4 border-b border-[#E7E5DE]">
                  <div className="flex items-center gap-3">
                    <button onClick={() => navigate("/app")} className="text-[#6B7280]"><ArrowLeft size={16} /></button>
                    <div>
                      <div className="flex items-center gap-2">
                        <h1 className="text-base font-semibold">{detail.conversation.lead_name || "Unnamed lead"}</h1>
                        <span className="text-[11px] text-[#9AA1AC]" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>
                          {detail.conversation.case_id ? detail.conversation.case_id.slice(0, 8) : detail.conversation.conversation_id.slice(0, 8)}
                        </span>
                      </div>
                      <p className="text-xs text-[#6B7280] mt-0.5">{detail.conversation.channel} · {detail.conversation.status.replaceAll("_", " ")}</p>
                    </div>
                  </div>
                  {stateInfo && <StatePill state={stateInfo.caseState} />}
                </header>

                <div className="flex-1 overflow-y-auto px-6 py-6 flex flex-col gap-3">
                  {detail.messages.length === 0 && (
                    <p className="text-sm text-[#6B7280] text-center mt-8">No messages in this conversation yet.</p>
                  )}
                  {detail.messages.map((m) => (
                    <div key={m.message_id} className={`flex flex-col ${m.direction === "inbound" ? "items-start" : "items-end"}`}>
                      <div
                        className={`text-sm max-w-md px-3.5 py-2.5 rounded-2xl ${m.direction === "inbound" ? "rounded-bl-sm" : "rounded-br-sm"}`}
                        style={m.direction === "inbound" ? { backgroundColor: "#F1F1EF" } : { backgroundColor: "#3A3EA6", color: "#fff" }}
                      >
                        {m.text}
                      </div>
                      <span className="text-[10px] text-[#9AA1AC] mt-1 px-1">
                        {m.role === "customer" ? detail.conversation.lead_name || "Customer" : m.role === "human" ? "You" : "Engine"} · {formatRelativeTime(m.created_at)}
                      </span>
                    </div>
                  ))}
                </div>

                <div className="border-t border-[#E7E5DE] p-4">
                  <div className="flex items-end gap-2">
                    <textarea
                      value={reply}
                      onChange={(e) => setReply(e.target.value)}
                      placeholder="Reply as your business... (sending isn't wired to the engine yet)"
                      rows={2}
                      disabled
                      className="flex-1 px-3.5 py-2.5 rounded-lg border border-[#E7E5DE] bg-[#FAFAF7] text-sm outline-none resize-none opacity-70"
                    />
                    <button disabled title="Replying isn't wired to the engine yet" className="h-10 w-10 shrink-0 rounded-lg flex items-center justify-center text-white opacity-40 cursor-not-allowed" style={{ backgroundColor: "#171A21" }}>
                      <Send size={15} />
                    </button>
                  </div>
                  <p className="mt-2 text-xs text-[#9AA1AC]">Replying and mark-resolved aren't wired to the engine yet — this reads real conversation history.</p>
                </div>
              </>
            )}
          </div>

          <div className="w-80 shrink-0 border-l border-[#E7E5DE] p-5 hidden lg:flex flex-col gap-6">
            {stateInfo && (
              <div>
                <div className="text-xs font-medium text-[#9AA1AC] mb-2">Where this case is</div>
                <Stepper stage={stateInfo.stage} color="#3A3EA6" />
                <div className="flex justify-between mt-1.5">
                  {STAGES.map((s) => <span key={s} className="text-[10px] text-[#9AA1AC]" style={{ width: 40 }}>{s}</span>)}
                </div>
              </div>
            )}
            <div className="flex items-center gap-4 text-xs text-[#6B7280]">
              <span className="flex items-center gap-1.5"><Phone size={12} /> {caseDetail?.lead.phone || "Not on file"}</span>
              <span className="flex items-center gap-1.5"><Mail size={12} /> {caseDetail?.lead.email || "Not on file"}</span>
            </div>
            <div>
              <div className="text-xs font-medium text-[#9AA1AC] mb-3" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>
                {caseDetail ? `${caseDetail.case_id.slice(0, 8)} · audit trail` : "audit trail"}
              </div>
              {!caseDetail ? (
                <p className="text-xs text-[#9AA1AC]">This conversation isn't linked to a case yet.</p>
              ) : (
                <div className="flex flex-col gap-2.5 text-sm">
                  {caseDetail.events.map((e) => {
                    const meta = describeEvent(e.event_type);
                    return (
                      <div key={e.event_id} className="flex gap-3">
                        <span className="text-[#9AA1AC] shrink-0" style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 12 }}>
                          {new Date(e.occurred_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                        </span>
                        <span className="font-medium shrink-0 w-16">{meta.stage}</span>
                        <span className="text-[#6B7280]">{meta.label}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
