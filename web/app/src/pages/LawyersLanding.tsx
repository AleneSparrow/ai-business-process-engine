import { ArrowRight, ShieldCheck, Check, MessageSquare, Scale, CalendarCheck, UserCheck, FileWarning, Clock } from "lucide-react";
import {
  DealCycle,
  FaqItem,
  MarketingShell,
  MARKETING_DISPLAY,
  usePrimaryCta,
} from "../components/MarketingShell";
import { salesWidgetConfigured } from "../components/FlywheelSalesWidget";

/**
 * Wave 1 campaign page — solo family-law / general-practice attorneys in
 * CA & NY. Separate from the product homepage so outreach can land here
 * without making Flywheel "a lawyer product". Starter only; Pro is not
 * sold as team routing (not built). Compliance is the proof of safety,
 * not the reason to buy — the reason to buy is losing $649 leads after hours.
 */

function StatChip({ n, label }: { n: string; label: string }) {
  return (
    <div className="bg-white rounded-xl border border-[#E7E5DE] p-4">
      <div style={{ fontFamily: MARKETING_DISPLAY, fontWeight: 600, color: "#B87333" }} className="text-2xl mb-1">
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

export default function LawyersLanding() {
  const { navigate, target } = usePrimaryCta();

  return (
    <MarketingShell
      variant="attorneys"
      title="Flywheel for solo attorneys — intake through booked consult"
      description="AI that answers and qualifies every inbound lead for your practice, then books the consult — architected so it cannot give legal advice. $199/mo, 7-day trial."
    >
      <section className="max-w-4xl mx-auto px-6 pt-16 md:pt-24 pb-14 text-center">
        <div
          className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full mb-6"
          style={{ backgroundColor: "#F5E7D6", color: "#B87333" }}
        >
          <Scale size={12} /> Solo & small practices — California & New York first
        </div>
        <h1 className="text-4xl md:text-5xl leading-[1.1] mb-5" style={{ fontFamily: MARKETING_DISPLAY, fontWeight: 600 }}>
          Every inquiry answered. Every consult on the calendar.
        </h1>
        <p className="text-base md:text-lg text-[#6B6459] leading-relaxed mb-6 max-w-2xl mx-auto">
          When a person contacts your firm and you are in court, with a client, or off the clock, Flywheel carries them to a booked consult — on a script the AI cannot talk itself out of.
        </p>
        <div className="flex justify-center mb-8">
          <DealCycle compact />
        </div>
        <div className="flex flex-wrap items-center justify-center gap-3">
          <button
            onClick={() => navigate(target)}
            className="text-sm font-bold uppercase tracking-wide px-5 py-3 rounded flex items-center gap-2"
            style={{ backgroundColor: "#D97B29", color: "#1C1206" }}
          >
            Start your 7-day free trial <ArrowRight size={15} />
          </button>
          <a href="#different" className="text-sm font-medium px-5 py-3 rounded-lg border border-[#151515]">
            See how it stays inside the script
          </a>
        </div>
        <span className="block text-xs text-[#9C9488] mt-4">$199/mo after trial · card required, no charge until trial ends</span>
        {salesWidgetConfigured() && (
          <p className="text-sm mt-4" style={{ color: "#B87333" }}>
            The chat in the corner is live Flywheel — this page is running the product, not a demo script.
          </p>
        )}
      </section>

      <section className="border-y border-[#E7E5DE] bg-white">
        <div className="max-w-6xl mx-auto px-6 py-6 flex items-center justify-center gap-3 text-sm text-[#9C9488] text-center">
          <ShieldCheck size={15} className="shrink-0" /> Discloses itself as AI, every time — built for the standard California (SB 243) and New York (Article 47) already require.
        </div>
      </section>

      <section className="max-w-4xl mx-auto px-6 py-16 md:py-20">
        <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "#B87333" }}>
          The problem
        </span>
        <h2 className="text-2xl md:text-3xl mt-2 mb-5" style={{ fontFamily: MARKETING_DISPLAY, fontWeight: 600 }}>
          Every missed call is a lead you already paid for.
        </h2>
        <p className="text-base text-[#6B6459] leading-relaxed max-w-2xl mb-8">
          The average cost per lead in legal services runs close to $649 — and most callers who hit voicemail never call back. A full-time intake specialist costs $55,000–$80,000 a year fully loaded, and even a great one can't answer at 11pm on a Sunday.
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
          <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "#B87333" }}>
            How Flywheel is different
          </span>
          <h2 className="text-2xl md:text-3xl mt-2 mb-6" style={{ fontFamily: MARKETING_DISPLAY, fontWeight: 600 }}>
            An architecture, not a prompt.
          </h2>
          <p className="text-base text-[#6B6459] leading-relaxed mb-6 max-w-2xl">
            Most AI intake tools are a chatbot wrapped around a general-purpose language model, steered by a prompt. Prompts can be argued with, jailbroken, or simply drift over a long conversation — and for a law firm, that's not a UX risk, it's a bar-complaint risk.
          </p>
          <p className="text-base text-[#6B6459] leading-relaxed mb-8 max-w-2xl">
            Flywheel works differently. The AI never decides what to tell your client — it only rewrites the wording of a script you control (your "Business DNA"). Qualification, booking, follow-up, and what the assistant is allowed to say all live in the engine, not in a prompt it could talk itself out of.
          </p>
          <div className="grid sm:grid-cols-2 gap-4 mb-8">
            <div className="rounded-xl border border-[#E7E5DE] bg-[#F5F1EA] p-6">
              <div className="text-xs font-semibold uppercase tracking-wide text-[#6B6459] mb-4">A chatbot on a prompt</div>
              <ul className="flex flex-col gap-3 text-sm text-[#6B6459]">
                <li className="pt-3 border-t border-[#E7E5DE] first:pt-0 first:border-0">The AI decides what to say, guided by instructions</li>
                <li className="pt-3 border-t border-[#E7E5DE]">Can be talked into estimating a case or promising an outcome</li>
                <li className="pt-3 border-t border-[#E7E5DE]">Compliance depends on the prompt holding up under pressure</li>
                <li className="pt-3 border-t border-[#E7E5DE]">Stops at capturing a name — a person still has to close the loop</li>
              </ul>
            </div>
            <div className="rounded-xl p-6" style={{ backgroundColor: "#151515" }}>
              <div className="text-xs font-semibold uppercase tracking-wide mb-4" style={{ color: "#D89456" }}>
                Flywheel
              </div>
              <ul className="flex flex-col gap-3 text-sm" style={{ color: "#E7E2D5" }}>
                <li className="pt-3 border-t first:pt-0 first:border-0" style={{ borderColor: "#33302B" }}>
                  The AI only rewrites the wording of a script you approve
                </li>
                <li className="pt-3 border-t" style={{ borderColor: "#33302B" }}>
                  Has no path to invent legal analysis or promise a result
                </li>
                <li className="pt-3 border-t" style={{ borderColor: "#33302B" }}>
                  Compliance is a hard limit in the message pipeline, not a prompt
                </li>
                <li className="pt-3 border-t" style={{ borderColor: "#33302B" }}>
                  Keeps going through qualification, booking, and follow-up
                </li>
              </ul>
            </div>
          </div>
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

      <section className="max-w-4xl mx-auto px-6 py-16 md:py-20">
        <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "#B87333" }}>
          What it does
        </span>
        <h2 className="text-2xl md:text-3xl mt-2 mb-7" style={{ fontFamily: MARKETING_DISPLAY, fontWeight: 600 }}>
          From the first message to a booked consult.
        </h2>
        <ul className="flex flex-col gap-3.5 max-w-lg">
          <DoesItem text="Answers inbound messages on your website, day or night" />
          <DoesItem text="Qualifies against the criteria you set — practice area, urgency, location" />
          <DoesItem text="Books a consultation so you walk into the meeting prepared" />
          <DoesItem text="Follows up if they go quiet — most people do not book on the first reply" />
          <DoesItem text="Escalates to you exactly when your rules say to" />
          <DoesItem text="Never estimates outcomes, gives legal advice, or promises a result — by design" />
        </ul>
      </section>

      <section className="bg-white border-y border-[#E7E5DE]">
        <div className="max-w-4xl mx-auto px-6 py-14 md:py-16 flex flex-col md:flex-row items-start md:items-center gap-6 justify-between">
          <div>
            <h2 className="text-xl mb-2" style={{ fontFamily: MARKETING_DISPLAY, fontWeight: 600 }}>
              Built for solo practices
            </h2>
            <p className="text-sm text-[#6B6459] leading-relaxed max-w-lg">
              Flywheel Starter is one attorney, one jurisdiction — set up in about 20 minutes, no developer. The same engine also runs other businesses; this page is written for your practice.
            </p>
          </div>
          <div className="flex items-center gap-2 text-sm font-medium shrink-0 px-4 py-2.5 rounded-lg" style={{ backgroundColor: "#F5E7D6", color: "#B87333" }}>
            <CalendarCheck size={16} /> ~20 minutes to go live
          </div>
        </div>
      </section>

      <section id="pricing" className="max-w-2xl mx-auto px-6 py-16 md:py-20 text-center">
        <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "#B87333" }}>
          Pricing
        </span>
        <h2 className="text-2xl md:text-3xl mt-2 mb-8" style={{ fontFamily: MARKETING_DISPLAY, fontWeight: 600 }}>
          One plan, built for one attorney.
        </h2>
        <div className="bg-white rounded-2xl border border-[#E7E5DE] p-8 md:p-10 text-left">
          <div className="flex items-baseline justify-between mb-1">
            <span className="text-sm font-semibold" style={{ fontFamily: MARKETING_DISPLAY }}>
              Starter
            </span>
            <span className="text-3xl" style={{ fontFamily: MARKETING_DISPLAY, fontWeight: 600 }}>
              $199<span className="text-sm text-[#6B6459] font-normal">/mo</span>
            </span>
          </div>
          <p className="text-sm text-[#6B6459] mb-6">7-day free trial. Card required at signup, no charge until the trial ends. Cancel anytime.</p>
          <ul className="flex flex-col gap-2.5 mb-7">
            <DoesItem text="One attorney, one jurisdiction — full deterministic compliance architecture" />
            <DoesItem text="24/7 web chat: qualify, book, follow up" />
            <DoesItem text="Complete audit trail on every conversation" />
            <DoesItem text="AI disclosure badge and compliance disclaimer, built in" />
          </ul>
          <button
            onClick={() => navigate(target)}
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
          <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "#B87333" }}>
            FAQ
          </span>
          <h2 className="text-2xl md:text-3xl mt-2 mb-6" style={{ fontFamily: MARKETING_DISPLAY, fontWeight: 600 }}>
            Questions attorneys ask first
          </h2>
          <FaqItem
            q="Is this actually compliant with my state's bar rules?"
            a={`Flywheel is built to support the disclosure requirements already in effect in states like California (SB 243) and New York (Article 47) — the AI identifies itself clearly, includes a "not legal advice" notice, and always offers a path to a human. Bar rules vary by state; read your own state's guidance before launch — we're not your compliance counsel.`}
          />
          <FaqItem
            q="Can the AI give legal advice by accident?"
            a="No — and that's the point. The AI only rewrites wording inside the script you approve. It has no path to invent legal analysis, estimate outcomes, or promise results, because that capability isn't built into the message pipeline."
          />
          <FaqItem q="How long does setup take?" a="About 20 minutes for a single-attorney practice. No developer needed. Then paste one snippet on your website." />
          <FaqItem
            q="What if I want more than one attorney on the account?"
            a="Multi-attorney support is on our roadmap — reach out and we'll let you know when it's ready for your firm."
          />
          <FaqItem
            q="Does it stop after the first reply?"
            a="No. Most people do not book a consult on the first message. Flywheel follows up on a schedule you approve, then stops when they book, decline, or you take over."
          />
          <FaqItem
            q="Is Flywheel only for law firms?"
            a="No. Attorneys are the first people we are talking to. The product has no legal-only mode — the same setup works for any business that already gets inbound inquiries."
          />
        </div>
      </section>

      <section className="max-w-4xl mx-auto px-6 py-20 md:py-28 text-center">
        <MessageSquare size={28} color="#B87333" className="mx-auto mb-5" />
        <h2 className="text-3xl md:text-4xl mb-4" style={{ fontFamily: MARKETING_DISPLAY, fontWeight: 600 }}>
          Someone is writing your firm right now.
        </h2>
        <p className="text-[#6B6459] mb-8 max-w-md mx-auto">7-day free trial, live in about 20 minutes, no setup call required.</p>
        <button
          onClick={() => navigate(target)}
          className="text-sm font-bold uppercase tracking-wide px-6 py-3.5 rounded inline-flex items-center gap-2"
          style={{ backgroundColor: "#D97B29", color: "#1C1206" }}
        >
          Start your 7-day free trial <ArrowRight size={15} />
        </button>
      </section>
    </MarketingShell>
  );
}
