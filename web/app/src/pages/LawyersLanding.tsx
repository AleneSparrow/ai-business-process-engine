import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight, ShieldCheck, Menu, X, Check, MessageSquare, Scale,
  CalendarCheck, UserCheck, FileWarning, Clock,
} from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { FlywheelMark } from "../components/Shared";

/**
 * Wave 1 GTM landing -- solo family-law / general-practice attorneys,
 * California and New York first.
 *
 * Copy hierarchy (flywheel-wave1-outreach-ad-materials.md, 24 Aug):
 * full cycle first, compliance second as objection-handling. Intake is the
 * wrong category. Legal is the entry wave, not the product identity -- the
 * homepage stays horizontal; this route is the vertical door.
 *
 * Starter ($199/mo) only. Do not promise payment collection, lead generation,
 * Pro / multi-attorney routing, or Google Calendar sync.
 */

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

export default function LawyersLanding() {
  const [menuOpen, setMenuOpen] = useState(false);
  const navigate = useNavigate();
  const { user } = useAuth();

  const primaryCtaTarget = user ? (user.business_ids.length > 0 ? "/app" : "/onboarding") : "/signup";

  useEffect(() => {
    document.title = "Flywheel — from inquiry to a booked consultation";
  }, []);

  return (
    <div style={{ backgroundColor: "#F5F1EA", fontFamily: "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif", color: "#151515" }} className="min-h-screen w-full">
      <header className="sticky top-0 z-20 backdrop-blur-sm" style={{ backgroundColor: "#F5F1EAEE", borderBottom: "1px solid #E7E5DE" }}>
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <button onClick={() => navigate("/")} className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg flex items-center justify-center text-white" style={{ backgroundColor: "#B87333" }}>
              <FlywheelMark size={16} />
            </div>
            <span className="font-semibold text-sm" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif" }}>Flywheel</span>
          </button>
          <nav className="hidden md:flex items-center gap-8 text-xs font-medium uppercase tracking-wider text-[#6B6459]">
            <a href="#different" className="hover:text-[#151515] transition-colors">How it's different</a>
            <a href="#pricing" className="hover:text-[#151515] transition-colors">Pricing</a>
            <a href="#faq" className="hover:text-[#151515] transition-colors">FAQ</a>
          </nav>
          <div className="hidden md:flex items-center gap-3">
            {!user && (
              <button onClick={() => navigate("/login")} className="text-sm font-medium text-[#6B6459]">Sign in</button>
            )}
            <button
              onClick={() => navigate(primaryCtaTarget)}
              className="text-xs font-bold uppercase tracking-wide px-4 py-2 rounded flex items-center gap-1.5"
              style={{ backgroundColor: "#D97B29", color: "#1C1206" }}
            >
              Start free trial <ArrowRight size={14} />
            </button>
          </div>
          <button className="md:hidden" onClick={() => setMenuOpen(!menuOpen)}>
            {menuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
        {menuOpen && (
          <div className="md:hidden px-6 pb-4 flex flex-col gap-3 text-xs font-medium uppercase tracking-wider text-[#6B6459]">
            <a href="#different">How it's different</a>
            <a href="#pricing">Pricing</a>
            <a href="#faq">FAQ</a>
            {!user && <button onClick={() => navigate("/login")} className="text-left">Sign in</button>}
            <button onClick={() => navigate(primaryCtaTarget)} className="font-bold px-4 py-2 rounded mt-1" style={{ backgroundColor: "#D97B29", color: "#1C1206" }}>
              Start free trial
            </button>
          </div>
        )}
      </header>

      <section className="max-w-4xl mx-auto px-6 pt-16 md:pt-24 pb-14 text-center">
        <div className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full mb-6" style={{ backgroundColor: "#F5E7D6", color: "#B87333" }}>
          <Scale size={12} /> Solo practices — California and New York
        </div>
        <h1 className="text-4xl md:text-5xl leading-[1.1] mb-5" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}>
          Most intake tools stop at “we'll get back to you.”
        </h1>
        <p className="text-base md:text-lg text-[#6B6459] leading-relaxed mb-8 max-w-2xl mx-auto">
          Flywheel qualifies the caller, answers the cost question with facts you approved, follows up with people who go quiet, and books the consultation. You get a prepared matter, not a message to return.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-3">
          <button
            onClick={() => navigate(primaryCtaTarget)}
            className="text-sm font-bold uppercase tracking-wide px-5 py-3 rounded flex items-center gap-2"
            style={{ backgroundColor: "#D97B29", color: "#1C1206" }}
          >
            Start your 7-day free trial <ArrowRight size={15} />
          </button>
          <a href="#different" className="text-sm font-medium px-5 py-3 rounded-lg border border-[#151515]">
            See how it works
          </a>
        </div>
        <span className="block text-xs text-[#9C9488] mt-4">$199/mo after trial · card required, no charge until trial ends · live in about 20 minutes</span>
      </section>

      <section className="border-y border-[#E7E5DE] bg-white">
        <div className="max-w-6xl mx-auto px-6 py-6 flex items-center justify-center gap-3 text-sm text-[#9C9488] text-center">
          <ShieldCheck size={15} className="shrink-0" /> Safe to put in front of a client: the AI rewords what you approved, and identifies itself in every conversation — the disclosure California (SB 243) and New York (Article 47) already require.
        </div>
      </section>

      <section className="max-w-4xl mx-auto px-6 py-16 md:py-20">
        <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "#B87333" }}>The problem</span>
        <h2 className="text-2xl md:text-3xl mt-2 mb-5" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}>
          Every missed call is a lead you already paid for.
        </h2>
        <p className="text-base text-[#6B6459] leading-relaxed max-w-2xl mb-8">
          The average cost per lead in legal services runs close to $649 — and most callers who hit
          voicemail never call back. Capture tools still leave qualifying, follow-up, and scheduling on you, usually the next business day.
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatChip n="$649" label="Avg. cost per lead, legal services" />
          <StatChip n="37.8%" label="Of inbound calls answered by a live person, industry-wide" />
          <StatChip n="85%" label="Of callers who hit voicemail never call back" />
          <StatChip n="$55–80K" label="Fully-loaded intake specialist, per year" />
        </div>
      </section>

      <section id="different" className="bg-white border-y border-[#E7E5DE]">
        <div className="max-w-4xl mx-auto px-6 py-16 md:py-20">
          <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "#B87333" }}>How Flywheel is different</span>
          <h2 className="text-2xl md:text-3xl mt-2 mb-6" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}>
            Capture is the easy half.
          </h2>
          <p className="text-base text-[#6B6459] leading-relaxed mb-8 max-w-2xl">
            Most tools built for firms stop at a name and a number in your inbox. Flywheel goes the rest of the way — on a script you approve, which the AI can reword but never improvise past.
          </p>
          <div className="grid sm:grid-cols-2 gap-4 mb-10">
            <div className="rounded-xl border border-[#E7E5DE] bg-[#F5F1EA] p-6">
              <div className="text-xs font-semibold uppercase tracking-wide text-[#6B6459] mb-4">An intake tool</div>
              <ul className="flex flex-col gap-3 text-sm text-[#6B6459]">
                <li className="pt-3 border-t border-[#E7E5DE] first:pt-0 first:border-0">Takes a name and a number</li>
                <li className="pt-3 border-t border-[#E7E5DE]">Drops a message in your inbox</li>
                <li className="pt-3 border-t border-[#E7E5DE]">Qualifying and scheduling still land on you</li>
                <li className="pt-3 border-t border-[#E7E5DE]">Quiet callers are not followed up</li>
              </ul>
            </div>
            <div className="rounded-xl p-6" style={{ backgroundColor: "#151515" }}>
              <div className="text-xs font-semibold uppercase tracking-wide mb-4" style={{ color: "#D89456" }}>Flywheel</div>
              <ul className="flex flex-col gap-3 text-sm" style={{ color: "#E7E2D5" }}>
                <li className="pt-3 border-t first:pt-0 first:border-0" style={{ borderColor: "#33302B" }}>Answers around the clock</li>
                <li className="pt-3 border-t" style={{ borderColor: "#33302B" }}>Asks your qualifying questions</li>
                <li className="pt-3 border-t" style={{ borderColor: "#33302B" }}>Handles cost hesitation using only facts you approved</li>
                <li className="pt-3 border-t" style={{ borderColor: "#33302B" }}>Books the consultation — you get a prepared matter</li>
              </ul>
            </div>
          </div>
          <h3 className="text-lg font-semibold mb-4" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif" }}>
            Why it's safe to put in front of a client
          </h3>
          <div className="grid sm:grid-cols-3 gap-4">
            <div className="rounded-xl border border-[#E7E5DE] p-5">
              <FileWarning size={18} color="#B87333" className="mb-3" />
              <div className="text-sm font-semibold mb-1">Can't estimate outcomes</div>
              <div className="text-xs text-[#6B6459] leading-relaxed">No path in the message pipeline to invent legal analysis or promise a result.</div>
            </div>
            <div className="rounded-xl border border-[#E7E5DE] p-5">
              <UserCheck size={18} color="#B87333" className="mb-3" />
              <div className="text-sm font-semibold mb-1">Always identifies as AI</div>
              <div className="text-xs text-[#6B6459] leading-relaxed">A visible disclosure stays on for the whole conversation, not buried in a footer.</div>
            </div>
            <div className="rounded-xl border border-[#E7E5DE] p-5">
              <Clock size={18} color="#B87333" className="mb-3" />
              <div className="text-sm font-semibold mb-1">Rewords, never decides</div>
              <div className="text-xs text-[#6B6459] leading-relaxed">The AI only rewrites wording inside a script you control. That limit is in the pipeline, not a prompt.</div>
            </div>
          </div>
        </div>
      </section>

      <section className="max-w-4xl mx-auto px-6 py-16 md:py-20">
        <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "#B87333" }}>What it does</span>
        <h2 className="text-2xl md:text-3xl mt-2 mb-7" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}>
          From inquiry to a booked consultation.
        </h2>
        <ul className="flex flex-col gap-3.5 max-w-lg">
          <DoesItem text="Answers inbound inquiries on your website, day or night" />
          <DoesItem text="Qualifies against the criteria you set — practice area and location" />
          <DoesItem text="Addresses cost and fit using only facts you approved" />
          <DoesItem text="Follows up with people who go quiet" />
          <DoesItem text="Books the consultation in Flywheel so you take the meeting prepared" />
          <DoesItem text="Escalates advice, emergencies, and hostility to you instead of improvising" />
        </ul>
      </section>

      <section className="bg-white border-y border-[#E7E5DE]">
        <div className="max-w-4xl mx-auto px-6 py-14 md:py-16 flex flex-col md:flex-row items-start md:items-center gap-6 justify-between">
          <div>
            <h2 className="text-xl mb-2" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}>Built for solo practices</h2>
            <p className="text-sm text-[#6B6459] leading-relaxed max-w-lg">
              Flywheel Starter is built for one attorney, one jurisdiction — set up in about
              20 minutes from what you tell it about your practice. Nothing in the engine is written specifically for law firms.
            </p>
          </div>
          <div className="flex items-center gap-2 text-sm font-medium shrink-0 px-4 py-2.5 rounded-lg" style={{ backgroundColor: "#F5E7D6", color: "#B87333" }}>
            <CalendarCheck size={16} /> ~20 minutes to go live
          </div>
        </div>
      </section>

      <section id="pricing" className="max-w-2xl mx-auto px-6 py-16 md:py-20 text-center">
        <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "#B87333" }}>Pricing</span>
        <h2 className="text-2xl md:text-3xl mt-2 mb-8" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}>
          One plan, built for one attorney.
        </h2>
        <div className="bg-white rounded-2xl border border-[#E7E5DE] p-8 md:p-10 text-left">
          <div className="flex items-baseline justify-between mb-1">
            <span className="text-sm font-semibold" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif" }}>Starter</span>
            <span className="text-3xl" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}>$199<span className="text-sm text-[#6B6459] font-normal">/mo</span></span>
          </div>
          <p className="text-sm text-[#6B6459] mb-6">7-day free trial. Card required at signup, no charge until the trial ends. Cancel anytime.</p>
          <ul className="flex flex-col gap-2.5 mb-7">
            <DoesItem text="Full cycle: qualify, follow up, and book the consultation" />
            <DoesItem text="24/7 web chat — prepared matter at hand-off, not an inbox dump" />
            <DoesItem text="AI rewords your script only — cannot give advice or estimate odds" />
            <DoesItem text="AI disclosure on by default (SB 243 / Article 47)" />
          </ul>
          <button
            onClick={() => navigate(primaryCtaTarget)}
            className="w-full text-sm font-bold uppercase tracking-wide px-5 py-3 rounded flex items-center justify-center gap-2"
            style={{ backgroundColor: "#D97B29", color: "#1C1206" }}
          >
            Start your 7-day free trial <ArrowRight size={15} />
          </button>
        </div>
        <p className="text-xs text-[#9C9488] mt-5">
          Multi-attorney support is on our roadmap — reach out and we'll let you know when it's ready for your firm.
        </p>
      </section>

      <section id="faq" className="bg-white border-t border-[#E7E5DE]">
        <div className="max-w-2xl mx-auto px-6 py-16 md:py-20">
          <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "#B87333" }}>FAQ</span>
          <h2 className="text-2xl md:text-3xl mt-2 mb-6" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}>Questions attorneys ask first</h2>
          <div>
            <FaqItem
              q="How is this different from the chatbot I was already pitched?"
              a="Those capture and hand off. Ask what happens after the form is filled: with most tools, it lands in your inbox. With Flywheel the qualifying questions get asked, the cost objection gets addressed with your own facts, and the consult gets booked. The handoff is a prepared matter."
            />
            <FaqItem
              q="Does this bring me new clients?"
              a="No. It works the inquiries you already get. Lead generation is a separate problem and we do not claim to solve it."
            />
            <FaqItem
              q="Does it collect payment from my client?"
              a="No. It reaches a booked consultation. Collecting the retainer stays with you."
            />
            <FaqItem
              q="What if it says something it shouldn't?"
              a="It cannot, structurally. The AI's only job is rewording content that already exists in your configuration. It has no path to generate a claim, a number, or an opinion that you did not put there."
            />
            <FaqItem
              q="Is this even allowed?"
              a={`The AI disclosure that California SB 243 and New York Article 47 require is on by default. On unauthorized practice of law: the architecture is designed so the assistant never gives advice. Confirm against your own state bar guidance — that is your professional obligation, not something a vendor can sign off for you.`}
            />
            <FaqItem q="How long does setup take?" a="About 20 minutes for a single-attorney practice. No developer needed, no per-firm build." />
            <FaqItem
              q="What if I want more than one attorney on the account?"
              a="Multi-attorney support is on our roadmap — reach out and we'll let you know when it's ready for your firm."
            />
          </div>
        </div>
      </section>

      <section className="max-w-4xl mx-auto px-6 py-20 md:py-28 text-center">
        <MessageSquare size={28} color="#B87333" className="mx-auto mb-5" />
        <h2 className="text-3xl md:text-4xl mb-4" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}>
          Someone is calling your firm right now.
        </h2>
        <p className="text-[#6B6459] mb-8 max-w-md mx-auto">7-day free trial, live in about 20 minutes, no setup call required.</p>
        <button
          onClick={() => navigate(primaryCtaTarget)}
          className="text-sm font-bold uppercase tracking-wide px-6 py-3.5 rounded inline-flex items-center gap-2"
          style={{ backgroundColor: "#D97B29", color: "#1C1206" }}
        >
          Start your 7-day free trial <ArrowRight size={15} />
        </button>
      </section>

      <footer className="border-t border-[#E7E5DE] py-8">
        <div className="max-w-6xl mx-auto px-6 flex items-center justify-between text-xs text-[#9C9488]">
          <span>© 2026 Flywheel</span>
          <button onClick={() => navigate("/")} className="hover:text-[#151515]">All businesses</button>
        </div>
      </footer>
    </div>
  );
}
