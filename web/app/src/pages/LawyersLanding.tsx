import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight, ShieldCheck, Menu, X, Check, MessageSquare, Scale,
  CalendarCheck, UserCheck, FileWarning, Clock,
} from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { FlywheelMark } from "../components/Shared";

/**
 * Wave 1 GTM landing page -- solo & small family-law / general-practice
 * attorneys, California & New York first (docs/marketing/04-gtm-legal-vertical.md,
 * docs/marketing/05-wave1-outreach-materials.md). Separate route from the
 * general Landing.tsx so outreach links (LinkedIn, cold email, Clio
 * marketplace) can point somewhere written for this exact audience without
 * touching the product's general-purpose homepage.
 *
 * Deliberate scope limits carried over from the GTM doc, not decoration:
 * - Starter ($199/mo) only. Pro is never mentioned as a "for your team" tier
 *   here -- multi-attorney routing isn't built yet (P1), and the GTM doc is
 *   explicit that selling Pro to a solo practice today creates disappointed
 *   early customers, not revenue.
 * - Compliance/architecture is the lead argument, not price. SetSmart is
 *   cheaper ($99) and not deterministic; that contrast is the whole pitch.
 * - The FAQ answers honestly that bar rules vary by state and this isn't
 *   legal advice about compliance -- matches the brand voice's "no
 *   superlatives" rule and avoids overclaiming into UPL-adjacent territory
 *   ourselves.
 */

function StatChip({ n, label }: { n: string; label: string }) {
  return (
    <div className="flex flex-col">
      <div style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }} className="text-2xl">
        {n}
      </div>
      <div className="text-xs text-[#6B6459] mt-0.5">{label}</div>
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

  const primaryCtaTarget = user ? (user.business_id ? "/app" : "/onboarding") : "/signup";

  return (
    <div style={{ backgroundColor: "#F5F1EA", fontFamily: "'Inter', sans-serif", color: "#151515" }} className="min-h-screen w-full">
      <header className="sticky top-0 z-20 backdrop-blur-sm" style={{ backgroundColor: "#F5F1EAEE", borderBottom: "1px solid #E7E5DE" }}>
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg flex items-center justify-center text-white" style={{ backgroundColor: "#B87333" }}>
              <FlywheelMark size={16} />
            </div>
            <span className="font-semibold text-sm" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>Flywheel</span>
          </div>
          <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-[#6B6459]">
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
              className="text-sm font-medium text-white px-4 py-2 rounded-lg flex items-center gap-1.5"
              style={{ backgroundColor: "#151515" }}
            >
              Start free trial <ArrowRight size={14} />
            </button>
          </div>
          <button className="md:hidden" onClick={() => setMenuOpen(!menuOpen)}>
            {menuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
        {menuOpen && (
          <div className="md:hidden px-6 pb-4 flex flex-col gap-3 text-sm font-medium text-[#6B6459]">
            <a href="#different">How it's different</a>
            <a href="#pricing">Pricing</a>
            <a href="#faq">FAQ</a>
            {!user && <button onClick={() => navigate("/login")} className="text-left">Sign in</button>}
            <button onClick={() => navigate(primaryCtaTarget)} className="text-white px-4 py-2 rounded-lg mt-1" style={{ backgroundColor: "#151515" }}>
              Start free trial
            </button>
          </div>
        )}
      </header>

      {/* ============ HERO ============ */}
      <section className="max-w-4xl mx-auto px-6 pt-16 md:pt-24 pb-14 text-center">
        <div className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full mb-6" style={{ backgroundColor: "#F5E7D6", color: "#B87333" }}>
          <Scale size={12} /> Built for solo & small practices — California &amp; New York
        </div>
        <h1 className="text-4xl md:text-5xl leading-[1.1] mb-5" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>
          The AI intake assistant that legally can't overstep.
        </h1>
        <p className="text-base md:text-lg text-[#6B6459] leading-relaxed mb-8 max-w-2xl mx-auto">
          Flywheel answers and qualifies every lead for your practice, 24/7 — built so the AI can only
          follow the script you approve. Not a policy. An architecture.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-3 mb-12">
          <button
            onClick={() => navigate(primaryCtaTarget)}
            className="text-sm font-medium text-white px-5 py-3 rounded-lg flex items-center gap-2"
            style={{ backgroundColor: "#151515" }}
          >
            Start your 7-day free trial <ArrowRight size={15} />
          </button>
          <span className="text-xs text-[#9C9488]">$199/mo after trial · card required, no charge until trial ends</span>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-10">
          <StatChip n="$649" label="Avg. cost per lead, legal services" />
          <StatChip n="$55–80K" label="Fully-loaded intake specialist, per year" />
          <StatChip n="24/7" label="Never misses an after-hours call" />
        </div>
      </section>

      <section className="border-y border-[#E7E5DE] bg-white">
        <div className="max-w-6xl mx-auto px-6 py-6 flex items-center justify-center gap-3 text-sm text-[#9C9488] text-center">
          <ShieldCheck size={15} className="shrink-0" /> Discloses itself as AI from the first message, every time — the standard California and New York already require, built in from day one.
        </div>
      </section>

      {/* ============ THE PROBLEM ============ */}
      <section className="max-w-4xl mx-auto px-6 py-16 md:py-20">
        <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "#B87333" }}>The problem</span>
        <h2 className="text-2xl md:text-3xl mt-2 mb-5" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>
          Every missed call is a lead you already paid for.
        </h2>
        <p className="text-base text-[#6B6459] leading-relaxed max-w-2xl">
          The average cost per lead in legal services runs close to $649 — and most callers who hit
          voicemail never call back. A full-time intake specialist costs $55,000–$80,000 a year fully
          loaded, and even a great one can't answer at 11pm on a Sunday.
        </p>
      </section>

      {/* ============ HOW IT'S DIFFERENT ============ */}
      <section id="different" className="bg-white border-y border-[#E7E5DE]">
        <div className="max-w-4xl mx-auto px-6 py-16 md:py-20">
          <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "#B87333" }}>How Flywheel is different</span>
          <h2 className="text-2xl md:text-3xl mt-2 mb-6" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>
            An architecture, not a prompt.
          </h2>
          <p className="text-base text-[#6B6459] leading-relaxed mb-6 max-w-2xl">
            Most AI intake tools are a chatbot wrapped around a general-purpose language model, steered
            by a prompt. Prompts can be argued with, jailbroken, or simply drift over a long conversation
            — and for a law firm, that's not a UX risk, it's a bar-complaint risk.
          </p>
          <p className="text-base text-[#6B6459] leading-relaxed mb-8 max-w-2xl">
            Flywheel works differently. The AI never decides what to tell your client — it only rewrites
            the wording of a script you control (your "Business DNA"). Case qualification, escalation
            rules, and what the assistant is and isn't allowed to say all live in the underlying engine,
            not in a prompt the AI could talk itself out of.
          </p>
          <div className="grid sm:grid-cols-3 gap-4">
            <div className="rounded-xl border border-[#E7E5DE] p-5">
              <FileWarning size={18} color="#B87333" className="mb-3" />
              <div className="text-sm font-semibold mb-1">Can't estimate outcomes</div>
              <div className="text-xs text-[#6B6459] leading-relaxed">No path in the message pipeline to invent legal analysis or promise a result.</div>
            </div>
            <div className="rounded-xl border border-[#E7E5DE] p-5">
              <UserCheck size={18} color="#B87333" className="mb-3" />
              <div className="text-sm font-semibold mb-1">Always identifies as AI</div>
              <div className="text-xs text-[#6B6459] leading-relaxed">A visible disclosure badge stays on screen for the whole conversation, not buried in a footer.</div>
            </div>
            <div className="rounded-xl border border-[#E7E5DE] p-5">
              <Clock size={18} color="#B87333" className="mb-3" />
              <div className="text-sm font-semibold mb-1">Same guarantee, every plan</div>
              <div className="text-xs text-[#6B6459] leading-relaxed">The compliance architecture isn't a premium feature — it's how every message gets built, always.</div>
            </div>
          </div>
        </div>
      </section>

      {/* ============ WHAT IT DOES ============ */}
      <section className="max-w-4xl mx-auto px-6 py-16 md:py-20">
        <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "#B87333" }}>What it does</span>
        <h2 className="text-2xl md:text-3xl mt-2 mb-7" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>
          One script, applied the same way every time.
        </h2>
        <ul className="flex flex-col gap-3.5 max-w-lg">
          <DoesItem text="Answers inbound leads on your website, day or night" />
          <DoesItem text="Qualifies the case against the criteria you set — practice area, urgency, location" />
          <DoesItem text="Books consultations directly onto your calendar" />
          <DoesItem text="Escalates to you exactly when your rules say to" />
          <DoesItem text="Never estimates case outcomes, gives legal advice, or promises a result — by design, not by request" />
        </ul>
      </section>

      {/* ============ BUILT FOR SOLO PRACTICES ============ */}
      <section className="bg-white border-y border-[#E7E5DE]">
        <div className="max-w-4xl mx-auto px-6 py-14 md:py-16 flex flex-col md:flex-row items-start md:items-center gap-6 justify-between">
          <div>
            <h2 className="text-xl mb-2" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>Built for solo practices</h2>
            <p className="text-sm text-[#6B6459] leading-relaxed max-w-lg">
              Flywheel Starter is built for exactly one attorney, one jurisdiction — set up in about
              20 minutes, no developer or IT help needed.
            </p>
          </div>
          <div className="flex items-center gap-2 text-sm font-medium shrink-0 px-4 py-2.5 rounded-lg" style={{ backgroundColor: "#F5E7D6", color: "#B87333" }}>
            <CalendarCheck size={16} /> ~20 minutes to go live
          </div>
        </div>
      </section>

      {/* ============ PRICING ============ */}
      <section id="pricing" className="max-w-2xl mx-auto px-6 py-16 md:py-20 text-center">
        <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "#B87333" }}>Pricing</span>
        <h2 className="text-2xl md:text-3xl mt-2 mb-8" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>
          One plan, built for one attorney.
        </h2>
        <div className="bg-white rounded-2xl border border-[#E7E5DE] p-8 md:p-10 text-left">
          <div className="flex items-baseline justify-between mb-1">
            <span className="text-sm font-semibold" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>Starter</span>
            <span className="text-3xl" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>$199<span className="text-sm text-[#6B6459] font-normal">/mo</span></span>
          </div>
          <p className="text-sm text-[#6B6459] mb-6">7-day free trial. Card required at signup, no charge until the trial ends. Cancel anytime.</p>
          <ul className="flex flex-col gap-2.5 mb-7">
            <DoesItem text="One attorney, one jurisdiction — full deterministic compliance architecture" />
            <DoesItem text="24/7 web chat intake, qualification, and booking" />
            <DoesItem text="Complete audit trail on every conversation" />
            <DoesItem text="AI disclosure badge and compliance disclaimer, built in" />
          </ul>
          <button
            onClick={() => navigate(primaryCtaTarget)}
            className="w-full text-sm font-medium text-white px-5 py-3 rounded-lg flex items-center justify-center gap-2"
            style={{ backgroundColor: "#151515" }}
          >
            Start your 7-day free trial <ArrowRight size={15} />
          </button>
        </div>
        <p className="text-xs text-[#9C9488] mt-5">
          Multi-attorney support is on our roadmap — reach out and we'll let you know when it's ready for your firm.
        </p>
      </section>

      {/* ============ FAQ ============ */}
      <section id="faq" className="bg-white border-t border-[#E7E5DE]">
        <div className="max-w-2xl mx-auto px-6 py-16 md:py-20">
          <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "#B87333" }}>FAQ</span>
          <h2 className="text-2xl md:text-3xl mt-2 mb-6" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>Questions attorneys ask first</h2>
          <div>
            <FaqItem
              q="Is this actually compliant with my state's bar rules?"
              a={`Flywheel is built to support the disclosure requirements already in effect in states like California and New York — the AI identifies itself clearly, includes a "not legal advice" notice, and always offers a path to a human. That said, bar rules vary by state, and we'd always recommend a quick read of your own state's guidance before launch — we're not your compliance counsel.`}
            />
            <FaqItem
              q="Can the AI give legal advice by accident?"
              a="No — and that's the point. The AI only rewrites wording inside the script you approve. It has no path to invent legal analysis, estimate outcomes, or promise results, because that capability isn't built into the message pipeline at all."
            />
            <FaqItem q="How long does setup take?" a="About 20 minutes for a single-attorney practice. No developer needed." />
            <FaqItem
              q="What if I want more than one attorney on the account?"
              a="Multi-attorney support is on our roadmap — reach out and we'll let you know when it's ready for your firm."
            />
          </div>
        </div>
      </section>

      {/* ============ FINAL CTA ============ */}
      <section className="max-w-4xl mx-auto px-6 py-20 md:py-28 text-center">
        <MessageSquare size={28} color="#B87333" className="mx-auto mb-5" />
        <h2 className="text-3xl md:text-4xl mb-4" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>
          Someone is calling your firm right now.
        </h2>
        <p className="text-[#6B6459] mb-8 max-w-md mx-auto">7-day free trial, live in about 20 minutes, no setup call required.</p>
        <button
          onClick={() => navigate(primaryCtaTarget)}
          className="text-sm font-medium text-white px-6 py-3.5 rounded-lg inline-flex items-center gap-2"
          style={{ backgroundColor: "#151515" }}
        >
          Start your 7-day free trial <ArrowRight size={15} />
        </button>
      </section>

      <footer className="border-t border-[#E7E5DE] py-8">
        <div className="max-w-6xl mx-auto px-6 flex items-center justify-between text-xs text-[#9C9488]">
          <span>© 2026 Flywheel</span>
          <span>Deterministic by design</span>
        </div>
      </footer>
    </div>
  );
}
