import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, MessageSquare, ShieldCheck, Zap, ChevronRight, Check, Menu, X } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { FlywheelMark } from "../components/Shared";

// Amber, not bronze -- this stepper visualizes a cycle in motion, and amber
// is the brand book's functional accent for "active, in motion" states.
function Stepper({ stage, color = "#D97B29" }: { stage: number; color?: string }) {
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
        <span className="text-xs font-medium text-[#9C9488]" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>
          your-business · web chat
        </span>
        <Stepper stage={step} />
      </div>
      <div className="flex flex-col gap-2.5">
        <div className="self-start bg-[#F1F1EF] rounded-2xl rounded-bl-sm px-3.5 py-2.5 text-sm max-w-[85%]">
          Hi — can someone come by this week? How much does it usually run?
        </div>
        <div
          className="self-end text-white rounded-2xl rounded-br-sm px-3.5 py-2.5 text-sm max-w-[85%]"
          style={{ backgroundColor: "#B87333" }}
        >
          I can help with that. What's the zip code, and which service are you looking for?
        </div>
        <div className="self-start bg-[#F1F1EF] rounded-2xl rounded-bl-sm px-3.5 py-2.5 text-sm max-w-[85%]">
          94110, a consult this week if you have an opening.
        </div>
      </div>
      <button
        onClick={() => setStep((s) => (s < 4 ? s + 1 : 2))}
        className="mt-4 text-xs font-medium text-[#B87333] flex items-center gap-1"
      >
        Advance step <ChevronRight size={12} />
      </button>
    </div>
  );
}

function StatChip({ n, label }: { n: string; label: string }) {
  return (
    <div className="bg-white rounded-xl border border-[#E7E5DE] p-4">
      <div style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600, color: "#B87333" }} className="text-2xl mb-1">
        {n}
      </div>
      <div className="text-xs text-[#6B6459] leading-snug">{label}</div>
    </div>
  );
}

function DoesItem({ text }: { text: string }) {
  return (
    <li className="flex items-start gap-2.5 text-sm text-[#151515]">
      <Check size={16} className="mt-0.5 shrink-0" color="#1E7B52" /> {text}
    </li>
  );
}

function FaqItem({ q, a }: { q: string; a: string }) {
  return (
    <div className="py-5 border-b border-[#E7E5DE] last:border-0">
      <div className="text-sm font-semibold mb-1.5">{q}</div>
      <div className="text-sm text-[#6B6459] leading-relaxed">{a}</div>
    </div>
  );
}

function Stage({ n, title, body }: { n: string; title: string; body: string }) {
  return (
    <div className="bg-[#F5F1EA] p-6">
      <div className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: "#96591f" }}>{n}</div>
      <h4 className="font-semibold mb-1.5" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif" }}>{title}</h4>
      <p className="text-sm text-[#6B6459] leading-relaxed">{body}</p>
    </div>
  );
}

export default function Landing() {
  const [menuOpen, setMenuOpen] = useState(false);
  const navigate = useNavigate();
  const { user } = useAuth();

  const primaryCtaTarget = user ? (user.business_ids.length > 0 ? "/app" : "/onboarding") : "/signup";
  const primaryCtaLabel = user ? "Go to dashboard" : "Start 7-day free trial";

  useEffect(() => {
    document.title = "Flywheel — from first inquiry to a booked job";
  }, []);

  return (
    <div style={{ backgroundColor: "#F5F1EA", fontFamily: "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif", color: "#151515" }} className="min-h-screen w-full">
      <header className="sticky top-0 z-20 backdrop-blur-sm" style={{ backgroundColor: "#F5F1EAEE", borderBottom: "1px solid #E7E5DE" }}>
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <button onClick={() => navigate("/")} className="flex items-center gap-2">
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center text-white"
              style={{ backgroundColor: "#B87333" }}
            >
              <FlywheelMark size={16} />
            </div>
            <span className="font-semibold text-sm" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif" }}>
              Flywheel
            </span>
          </button>
          <nav className="hidden md:flex items-center gap-8 text-xs font-medium uppercase tracking-wider text-[#6B6459]">
            <a href="#how" className="hover:text-[#151515] transition-colors">How it works</a>
            <a href="#pricing" className="hover:text-[#151515] transition-colors">Pricing</a>
            <a href="#faq" className="hover:text-[#151515] transition-colors">FAQ</a>
          </nav>
          <div className="hidden md:flex items-center gap-3">
            {!user && (
              <button onClick={() => navigate("/login")} className="text-sm font-medium text-[#6B6459]">
                Sign in
              </button>
            )}
            <button
              onClick={() => navigate(primaryCtaTarget)}
              className="text-xs font-bold uppercase tracking-wide px-4 py-2 rounded flex items-center gap-1.5"
              style={{ backgroundColor: "#D97B29", color: "#1C1206" }}
            >
              {primaryCtaLabel} <ArrowRight size={14} />
            </button>
          </div>
          <button className="md:hidden" onClick={() => setMenuOpen(!menuOpen)}>
            {menuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
        {menuOpen && (
          <div className="md:hidden px-6 pb-4 flex flex-col gap-3 text-xs font-medium uppercase tracking-wider text-[#6B6459]">
            <a href="#how">How it works</a>
            <a href="#pricing">Pricing</a>
            <a href="#faq">FAQ</a>
            {!user && (
              <button onClick={() => navigate("/login")} className="text-left">Sign in</button>
            )}
            <button onClick={() => navigate(primaryCtaTarget)} className="font-bold px-4 py-2 rounded mt-1" style={{ backgroundColor: "#D97B29", color: "#1C1206" }}>
              {primaryCtaLabel}
            </button>
          </div>
        )}
      </header>

      <section className="max-w-6xl mx-auto px-6 pt-16 md:pt-24 pb-16 grid md:grid-cols-2 gap-12 items-center">
        <div>
          <div className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full mb-6" style={{ backgroundColor: "#F5E7D6", color: "#B87333" }}>
            <Zap size={12} /> From inquiry to a booked job — any business
          </div>
          <h1 className="text-4xl md:text-5xl leading-[1.08] mb-5" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}>
            Capture is the easy half.
          </h1>
          <p className="text-base text-[#6B6459] leading-relaxed mb-8 max-w-md">
            Most tools take a name and a number and hand you a message to return.{" "}
            <span className="text-[#151515] font-medium">Flywheel carries the inquiry the rest of the way</span> —
            qualifying, answering the price question, following up with people who go quiet, and booking the job.
            Works on any business, with no setup built for your company specifically.
          </p>
          <div className="flex flex-wrap items-center gap-3 mb-4">
            <button
              onClick={() => navigate(primaryCtaTarget)}
              className="text-sm font-bold uppercase tracking-wide px-5 py-3 rounded flex items-center gap-2"
              style={{ backgroundColor: "#D97B29", color: "#1C1206" }}
            >
              {user ? "Go to dashboard" : "Start 7-day free trial"} <ArrowRight size={15} />
            </button>
            <a href="#how" className="text-sm font-medium px-5 py-3 rounded-lg border border-[#151515]">
              See how it works
            </a>
          </div>
          <p className="text-xs text-[#9C9488]">Live in about 20 minutes · No setup call · $199/mo after trial</p>
        </div>
        <div className="flex justify-center md:justify-end"><ChatBubble /></div>
      </section>

      <section className="border-y border-[#E7E5DE] bg-white">
        <div className="max-w-6xl mx-auto px-6 py-6 flex items-center justify-center gap-3 text-sm text-[#9C9488] text-center">
          <ShieldCheck size={15} className="shrink-0" /> Every conversation says it is an AI. Disclosure is on by default, not an option you have to find.
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-6 py-16 md:py-20">
        <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "#B87333" }}>The problem</span>
        <h2 className="text-2xl md:text-3xl mt-2 mb-5" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}>
          The lead already cost you money. Then it waited.
        </h2>
        <p className="text-base text-[#6B6459] leading-relaxed max-w-2xl mb-8">
          You paid to make the phone ring. What happens in the next five minutes decides whether that spend turns into work — and for most businesses, nothing happens for two days.
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatChip n="47 hrs" label="Average time businesses take to respond to an inbound lead" />
          <StatChip n="100×" label="Higher odds of reaching a lead answering in 5 minutes instead of 30" />
          <StatChip n="78%" label="Of customers buy from whoever responds to them first" />
          <StatChip n="85%" label="Of people who reach voicemail never call back" />
        </div>
      </section>

      <section id="how" className="bg-white border-y border-[#E7E5DE]">
        <div className="max-w-6xl mx-auto px-6 py-16 md:py-20">
          <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "#B87333" }}>How it works</span>
          <h2 className="text-2xl md:text-3xl mt-2 mb-3" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}>
            It runs the whole conversation, not the first message.
          </h2>
          <p className="text-base text-[#6B6459] leading-relaxed max-w-2xl mb-8">
            The same engine handles every stage. Nothing here is written for one industry — it adapts from what you tell it about your business.
          </p>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-px bg-[#E7E5DE] rounded-xl overflow-hidden border border-[#E7E5DE]">
            <Stage n="01" title="Answers immediately" body="Every inquiry gets a reply in seconds, at 2am and on Sunday, on your website or by text." />
            <Stage n="02" title="Qualifies" body="Asks the questions you defined, in plain conversation. Understands what people actually write." />
            <Stage n="03" title="Handles the hesitation" body={"\"How much is this?\" gets answered with facts from your configuration — never an invented discount or promise."} />
            <Stage n="04" title="Follows up" body="People go quiet. It comes back on your schedule, only where the customer agreed to be contacted." />
            <Stage n="05" title="Books it" body="Offers real times and confirms the appointment, or puts your quote in front of the customer for approval." />
            <div className="p-6" style={{ backgroundColor: "#151515" }}>
              <div className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: "#D89456" }}>Hand-off</div>
              <h4 className="font-semibold mb-1.5 text-[#F5F1EA]" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif" }}>You get a prepared job</h4>
              <p className="text-sm leading-relaxed" style={{ color: "#b9b2a2" }}>Not a voicemail to return. Emergencies, hostility, and anything asking for advice go to a person instead.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-6 py-16 md:py-20">
        <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "#B87333" }}>Why it's different</span>
        <h2 className="text-2xl md:text-3xl mt-2 mb-8" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}>
          Most tools stop where the work starts.
        </h2>
        <div className="grid md:grid-cols-2 gap-5">
          <div className="rounded-xl border border-[#E7E5DE] bg-[#EEE8DC] p-7">
            <div className="text-xs font-semibold uppercase tracking-wide text-[#6B6459] mb-4">An intake tool or chatbot</div>
            <ul className="flex flex-col gap-3 text-sm text-[#6B6459]">
              <li className="pt-3 border-t border-[#E7E5DE] first:pt-0 first:border-0">Collects a name and a number</li>
              <li className="pt-3 border-t border-[#E7E5DE]">Drops it in your inbox</li>
              <li className="pt-3 border-t border-[#E7E5DE]">Qualifying is still your job</li>
              <li className="pt-3 border-t border-[#E7E5DE]">Nobody chases the ones who go quiet</li>
              <li className="pt-3 border-t border-[#E7E5DE]">Scheduling happens the next business day</li>
            </ul>
          </div>
          <div className="rounded-xl p-7" style={{ backgroundColor: "#151515" }}>
            <div className="text-xs font-semibold uppercase tracking-wide mb-4" style={{ color: "#D89456" }}>Flywheel</div>
            <ul className="flex flex-col gap-3 text-sm" style={{ color: "#E7E2D5" }}>
              <li className="pt-3 border-t first:pt-0 first:border-0" style={{ borderColor: "#33302B" }}>Answers in seconds, around the clock</li>
              <li className="pt-3 border-t" style={{ borderColor: "#33302B" }}>Asks your qualifying questions in conversation</li>
              <li className="pt-3 border-t" style={{ borderColor: "#33302B" }}>Answers price and fit from your own facts</li>
              <li className="pt-3 border-t" style={{ borderColor: "#33302B" }}>Follows up with people who stopped replying</li>
              <li className="pt-3 border-t" style={{ borderColor: "#33302B" }}>Books the appointment or gets the quote approved</li>
            </ul>
          </div>
        </div>
      </section>

      <section className="bg-white border-y border-[#E7E5DE]">
        <div className="max-w-6xl mx-auto px-6 py-16 md:py-20">
          <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "#B87333" }}>Why it's safe</span>
          <h2 className="text-2xl md:text-3xl mt-2 mb-3" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}>
            The AI never decides what to say.
          </h2>
          <p className="text-base text-[#6B6459] leading-relaxed max-w-2xl mb-8">
            This is the part that lets a regulated business use it at all — not the reason to buy. The reason to buy is that the cycle finishes.
          </p>
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="rounded-xl border border-[#E7E5DE] p-5">
              <div className="text-sm font-semibold mb-1">It rewords, it doesn't invent</div>
              <div className="text-xs text-[#6B6459] leading-relaxed">Every outgoing message is a rewrite of content already in your configuration. No path to a price, a promise, or an opinion you did not put there.</div>
            </div>
            <div className="rounded-xl border border-[#E7E5DE] p-5">
              <div className="text-sm font-semibold mb-1">It says it's an AI, every time</div>
              <div className="text-xs text-[#6B6459] leading-relaxed">Persistent disclosure in every conversation — the kind California SB 243, New York Article 47, and EU AI Act Article 50 already ask for.</div>
            </div>
            <div className="rounded-xl border border-[#E7E5DE] p-5">
              <div className="text-sm font-semibold mb-1">It cannot offer what you didn't authorize</div>
              <div className="text-xs text-[#6B6459] leading-relaxed">No invented discounts, no guaranteed outcomes. Enforced where messages are assembled, not asked for in a prompt.</div>
            </div>
            <div className="rounded-xl border border-[#E7E5DE] p-5">
              <div className="text-sm font-semibold mb-1">It hands over instead of guessing</div>
              <div className="text-xs text-[#6B6459] leading-relaxed">Emergencies, hostile messages, and any request for advice go to a person. Being unsure is a reason to escalate, not to improvise.</div>
            </div>
          </div>
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-6 py-16 md:py-20">
        <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "#B87333" }}>Same engine</span>
        <h2 className="text-2xl md:text-3xl mt-2 mb-3" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}>
          Your industry's words. Not a rebuild.
        </h2>
        <p className="text-base text-[#6B6459] leading-relaxed max-w-2xl mb-8">
          There is no industry-specific version. Law practices are the first door we opened to customers, not what the product is built around.
        </p>
        <div className="grid md:grid-cols-3 gap-5">
          <button
            onClick={() => navigate("/lawyers")}
            className="text-left bg-white rounded-xl border border-[#E7E5DE] p-6 hover:shadow-md transition-shadow"
          >
            <div className="text-xs font-bold uppercase tracking-widest mb-3" style={{ color: "#B87333" }}>Available now</div>
            <h3 className="font-semibold mb-2" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif" }}>Law practices</h3>
            <p className="text-sm text-[#6B6459] leading-relaxed mb-3">Solo firms in California and New York — family law and general practice. Same engine, with the disclosure those states already require.</p>
            <span className="text-sm font-semibold" style={{ color: "#96591f" }}>See the legal version →</span>
          </button>
          <div className="bg-white rounded-xl border border-[#E7E5DE] p-6 opacity-70">
            <div className="text-xs font-bold uppercase tracking-widest text-[#9C9488] mb-3">Next</div>
            <h3 className="font-semibold mb-2" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif" }}>Financial and insurance advisors</h3>
            <p className="text-sm text-[#6B6459] leading-relaxed">Long consideration cycles, high replacement cost. The same qualifying and follow-up, on a longer conversation.</p>
          </div>
          <div className="bg-white rounded-xl border border-[#E7E5DE] p-6 opacity-70">
            <div className="text-xs font-bold uppercase tracking-widest text-[#9C9488] mb-3">On the roadmap</div>
            <h3 className="font-semibold mb-2" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif" }}>Home and field services</h3>
            <p className="text-sm text-[#6B6459] leading-relaxed">High inbound volume, urgent jobs, service-area screening already in the engine. Not a separate product.</p>
          </div>
        </div>
      </section>

      <section id="pricing" className="bg-white border-y border-[#E7E5DE]">
        <div className="max-w-2xl mx-auto px-6 py-16 md:py-20 text-center">
          <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "#B87333" }}>Pricing</span>
          <h2 className="text-2xl md:text-3xl mt-2 mb-3" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}>
            One plan. Nothing to negotiate.
          </h2>
          <p className="text-sm text-[#6B6459] mb-8">Card at signup, seven days free, cancel from your dashboard.</p>
          <div className="bg-[#F5F1EA] rounded-2xl border border-[#E7E5DE] p-8 md:p-10 text-left">
            <div className="flex items-baseline justify-between mb-1">
              <span className="text-sm font-semibold" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif" }}>Starter</span>
              <span className="text-3xl" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}>$199<span className="text-sm text-[#6B6459] font-normal">/mo</span></span>
            </div>
            <p className="text-sm text-[#6B6459] mb-6">For a single-operator business. 7-day free trial. No charge until the trial ends.</p>
            <ul className="flex flex-col gap-2.5 mb-7">
              <DoesItem text="The full cycle — qualifying, objections, follow-up, booking" />
              <DoesItem text="Unlimited conversations on your website and by text" />
              <DoesItem text="Zero per-company setup — no configuration call" />
              <DoesItem text="AI disclosure on by default in every conversation" />
              <DoesItem text="Human hand-off with the details already collected" />
            </ul>
            <button
              onClick={() => navigate(primaryCtaTarget)}
              className="w-full text-sm font-bold uppercase tracking-wide px-5 py-3 rounded flex items-center justify-center gap-2"
              style={{ backgroundColor: "#D97B29", color: "#1C1206" }}
            >
              {primaryCtaLabel} <ArrowRight size={15} />
            </button>
          </div>
        </div>
      </section>

      <section id="faq" className="max-w-2xl mx-auto px-6 py-16 md:py-20">
        <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "#B87333" }}>Straight answers</span>
        <h2 className="text-2xl md:text-3xl mt-2 mb-6" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}>
          What people ask before they start
        </h2>
        <FaqItem
          q="Does this bring me new customers?"
          a="No. Flywheel works the inquiries you already get — from your website, your ads, your referrals. Finding new leads is a different problem and we don't claim to solve it."
        />
        <FaqItem
          q="Does it take payment from my customer?"
          a="No. It gets to a confirmed booking or an approved quote and hands you a prepared job. Collecting the money stays with you, through whatever you already use."
        />
        <FaqItem
          q="What does no setup actually mean?"
          a="At signup you name your industry, describe what you do in a sentence, and list your services. That is the configuration. Nobody builds a version for your company."
        />
        <FaqItem
          q="Can it say something that gets me in trouble?"
          a="It can only reword content that already exists in your configuration. Requests for advice or a judgement call are escalated to you, not answered."
        />
        <FaqItem
          q="My business is nothing like a law firm. Will it work?"
          a="The engine contains no industry-specific logic. It reads your own description of what you do. Law practices are the first industry we opened to customers, not what the product is built around."
        />
      </section>

      <section className="max-w-6xl mx-auto px-6 py-20 md:py-28 text-center">
        <MessageSquare size={28} color="#B87333" className="mx-auto mb-5" />
        <h2 className="text-3xl md:text-4xl mb-4" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}>
          Stop returning voicemails.
        </h2>
        <p className="text-[#6B6459] mb-8 max-w-md mx-auto">Seven days free. About twenty minutes to go live. No call with anyone required.</p>
        <button
          onClick={() => navigate(primaryCtaTarget)}
          className="text-sm font-bold uppercase tracking-wide px-6 py-3.5 rounded inline-flex items-center gap-2"
          style={{ backgroundColor: "#D97B29", color: "#1C1206" }}
        >
          {primaryCtaLabel} <ArrowRight size={15} />
        </button>
      </section>

      <footer className="border-t border-[#E7E5DE] py-8">
        <div className="max-w-6xl mx-auto px-6 flex items-center justify-between text-xs text-[#9C9488]">
          <span>© 2026 Flywheel</span>
          <button onClick={() => navigate("/lawyers")} className="hover:text-[#151515]">For law practices</button>
        </div>
      </footer>
    </div>
  );
}
