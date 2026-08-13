import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, MessageSquare, Workflow, ShieldCheck, Zap, ChevronRight, Check, Menu, X } from "lucide-react";
import { useAuth } from "../auth/AuthContext";

function Stepper({ stage, color = "#3A3EA6" }: { stage: number; color?: string }) {
  const STAGES = ["Trigger", "Context", "Decision", "Action", "Result"];
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

function ChatBubble() {
  const [step, setStep] = useState(2);
  return (
    <div className="bg-white rounded-2xl border border-[#E7E5DE] shadow-[0_1px_2px_rgba(0,0,0,0.03)] p-5 w-full max-w-sm">
      <div className="flex items-center justify-between mb-4">
        <span className="text-xs font-medium text-[#9AA1AC]" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>
          acme-co · web chat
        </span>
        <Stepper stage={step} />
      </div>
      <div className="flex flex-col gap-2.5">
        <div className="self-start bg-[#F1F1EF] rounded-2xl rounded-bl-sm px-3.5 py-2.5 text-sm max-w-[85%]">
          Hi, I saw your pricing page — can someone walk me through getting started?
        </div>
        <div
          className="self-end text-white rounded-2xl rounded-br-sm px-3.5 py-2.5 text-sm max-w-[85%]"
          style={{ backgroundColor: "#3A3EA6" }}
        >
          Happy to help. What are you looking to get done, and what's your timeline?
        </div>
        <div className="self-start bg-[#F1F1EF] rounded-2xl rounded-bl-sm px-3.5 py-2.5 text-sm max-w-[85%]">
          Onboarding automation for ~50 leads/month, ideally live this month
        </div>
      </div>
      <button
        onClick={() => setStep((s) => (s < 4 ? s + 1 : 2))}
        className="mt-4 text-xs font-medium text-[#3A3EA6] flex items-center gap-1"
      >
        Advance step <ChevronRight size={12} />
      </button>
    </div>
  );
}

function StatBlock({ n, label }: { n: string; label: string }) {
  return (
    <div>
      <div style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }} className="text-3xl mb-1">
        {n}
      </div>
      <div className="text-sm text-[#6B7280]">{label}</div>
    </div>
  );
}

function FeatureCard({
  icon: Icon,
  title,
  body,
}: {
  icon: typeof MessageSquare;
  title: string;
  body: string;
}) {
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

function StepRow({ n, title, body, last }: { n: string; title: string; body: string; last?: boolean }) {
  return (
    <div className="flex gap-5">
      <div className="flex flex-col items-center">
        <div
          className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold shrink-0"
          style={{ backgroundColor: "#171A21", color: "#fff", fontFamily: "'Space Grotesk', sans-serif" }}
        >
          {n}
        </div>
        {!last && <div className="w-px flex-1 bg-[#E7E5DE] my-1" />}
      </div>
      <div className="pb-10">
        <h3 className="font-semibold mb-1.5">{title}</h3>
        <p className="text-sm text-[#6B7280] leading-relaxed max-w-md">{body}</p>
      </div>
    </div>
  );
}

export default function Landing() {
  const [menuOpen, setMenuOpen] = useState(false);
  const navigate = useNavigate();
  const { user } = useAuth();

  const primaryCtaTarget = user ? (user.business_id ? "/app" : "/onboarding") : "/signup";

  return (
    <div style={{ backgroundColor: "#F7F6F2", fontFamily: "'Inter', sans-serif", color: "#171A21" }} className="min-h-screen w-full">
      <header className="sticky top-0 z-20 backdrop-blur-sm" style={{ backgroundColor: "#F7F6F2EE", borderBottom: "1px solid #E7E5DE" }}>
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center text-white text-xs font-bold"
              style={{ backgroundColor: "#3A3EA6", fontFamily: "'Space Grotesk', sans-serif" }}
            >
              A
            </div>
            <span className="font-semibold text-sm" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              Atelier
            </span>
          </div>
          <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-[#6B7280]">
            <a href="#how" className="hover:text-[#171A21] transition-colors">How it works</a>
            <a href="#features" className="hover:text-[#171A21] transition-colors">Features</a>
            <a href="#trust" className="hover:text-[#171A21] transition-colors">Trust & audit</a>
          </nav>
          <div className="hidden md:flex items-center gap-3">
            {!user && (
              <button onClick={() => navigate("/login")} className="text-sm font-medium text-[#6B7280]">
                Sign in
              </button>
            )}
            <button
              onClick={() => navigate(primaryCtaTarget)}
              className="text-sm font-medium text-white px-4 py-2 rounded-lg flex items-center gap-1.5"
              style={{ backgroundColor: "#171A21" }}
            >
              {user ? "Go to dashboard" : "Get started"} <ArrowRight size={14} />
            </button>
          </div>
          <button className="md:hidden" onClick={() => setMenuOpen(!menuOpen)}>
            {menuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
        {menuOpen && (
          <div className="md:hidden px-6 pb-4 flex flex-col gap-3 text-sm font-medium text-[#6B7280]">
            <a href="#how">How it works</a>
            <a href="#features">Features</a>
            <a href="#trust">Trust & audit</a>
            {!user && (
              <button onClick={() => navigate("/login")} className="text-left">Sign in</button>
            )}
            <button onClick={() => navigate(primaryCtaTarget)} className="text-white px-4 py-2 rounded-lg mt-1" style={{ backgroundColor: "#171A21" }}>
              {user ? "Go to dashboard" : "Get started"}
            </button>
          </div>
        )}
      </header>

      <section className="max-w-6xl mx-auto px-6 pt-16 md:pt-24 pb-16 grid md:grid-cols-2 gap-12 items-center">
        <div>
          <div className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full mb-6" style={{ backgroundColor: "#EEEEF9", color: "#3A3EA6" }}>
            <Zap size={12} /> Adaptive to any business
          </div>
          <h1 className="text-4xl md:text-5xl leading-[1.08] mb-5" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>
            Every lead gets answered.<br />Every step gets logged.
          </h1>
          <p className="text-base text-[#6B7280] leading-relaxed mb-8 max-w-md">
            Atelier qualifies, books, and follows up with your customers the moment they message —
            then hands off to you the moment it should. Nothing happens off the record.
          </p>
          <div className="flex flex-wrap items-center gap-3 mb-10">
            <button
              onClick={() => navigate(primaryCtaTarget)}
              className="text-sm font-medium text-white px-5 py-3 rounded-lg flex items-center gap-2"
              style={{ backgroundColor: "#171A21" }}
            >
              Set up your business <ArrowRight size={15} />
            </button>
            <a href="#trust" className="text-sm font-medium px-5 py-3 rounded-lg border border-[#E7E5DE] bg-white">
              See how it stays accountable
            </a>
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
            <StepRow n="2" title="It qualifies against your rules" body="Your questions, required details, urgency — defined by you, applied every time, the same way." />
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
                ["09:41:03", "Context", "Matched existing lead by email"],
                ["09:41:04", "Decision", "Missing required field: project timeline"],
                ["09:41:04", "Action", "Sent clarifying question"],
                ["09:44:18", "Result", "Escalated — customer flagged this as urgent"],
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
        <button
          onClick={() => navigate(primaryCtaTarget)}
          className="text-sm font-medium text-white px-6 py-3.5 rounded-lg inline-flex items-center gap-2"
          style={{ backgroundColor: "#171A21" }}
        >
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
