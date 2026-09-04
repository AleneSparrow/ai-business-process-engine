import { useState } from "react";
import { ArrowRight, MessageSquare, Workflow, ShieldCheck, Zap, ChevronRight, Check } from "lucide-react";
import {
  DealCycle,
  FaqItem,
  MarketingShell,
  MARKETING_DISPLAY,
  usePrimaryCta,
} from "../components/MarketingShell";
import { salesWidgetConfigured } from "../components/FlywheelSalesWidget";

function ChatBubble() {
  const [step, setStep] = useState(1);
  const stage = step >= 3 ? "Booked" : "Qualifying";
  return (
    <div className="bg-white rounded-2xl border border-[#E7E5DE] shadow-[0_1px_2px_rgba(0,0,0,0.03)] p-5 w-full max-w-sm">
      <div className="flex items-center justify-between mb-4 gap-3">
        <span className="text-xs font-medium text-[#9C9488]" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>
          preview · what your visitor sees
        </span>
        <span
          className="text-[11px] font-medium uppercase tracking-wide px-2 py-0.5 rounded-full shrink-0"
          style={{
            backgroundColor: stage === "Booked" ? "#E9F5EF" : "#FBF0E2",
            color: stage === "Booked" ? "#1E7B52" : "#D97B29",
          }}
        >
          {stage}
        </span>
      </div>
      <div className="flex flex-col gap-2.5">
        <div className="self-start bg-[#F1F1EF] rounded-2xl rounded-bl-sm px-3.5 py-2.5 text-sm max-w-[85%]">
          Hi — can someone help me get started this week?
        </div>
        <div
          className="self-end text-white rounded-2xl rounded-br-sm px-3.5 py-2.5 text-sm max-w-[85%]"
          style={{ backgroundColor: "#B87333" }}
        >
          Happy to help. What do you need done, and what's your timeline?
        </div>
        <div className="self-start bg-[#F1F1EF] rounded-2xl rounded-bl-sm px-3.5 py-2.5 text-sm max-w-[85%]">
          A consult this month, weekday afternoons work.
        </div>
        {step >= 3 && (
          <div
            className="self-end text-white rounded-2xl rounded-br-sm px-3.5 py-2.5 text-sm max-w-[85%]"
            style={{ backgroundColor: "#B87333" }}
          >
            Thursday 3:00pm is open. Want me to book that?
          </div>
        )}
      </div>
      <button
        onClick={() => setStep((s) => (s < 3 ? s + 1 : 1))}
        className="mt-4 text-xs font-medium text-[#B87333] flex items-center gap-1"
      >
        Advance the deal <ChevronRight size={12} />
      </button>
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
      <div className="w-9 h-9 rounded-lg flex items-center justify-center mb-4" style={{ backgroundColor: "#F5E7D6" }}>
        <Icon size={17} color="#B87333" strokeWidth={2} />
      </div>
      <h3 className="font-semibold mb-1.5">{title}</h3>
      <p className="text-sm text-[#6B6459] leading-relaxed">{body}</p>
    </div>
  );
}

function StepRow({ n, title, body, last }: { n: string; title: string; body: string; last?: boolean }) {
  return (
    <div className="flex gap-5">
      <div className="flex flex-col items-center">
        <div
          className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold shrink-0"
          style={{ backgroundColor: "#151515", color: "#fff", fontFamily: MARKETING_DISPLAY }}
        >
          {n}
        </div>
        {!last && <div className="w-px flex-1 bg-[#E7E5DE] my-1" />}
      </div>
      <div className="pb-10">
        <h3 className="font-semibold mb-1.5">{title}</h3>
        <p className="text-sm text-[#6B6459] leading-relaxed max-w-md">{body}</p>
      </div>
    </div>
  );
}

const INDUSTRIES = [
  "Consulting",
  "Home services",
  "Coaching",
  "Legal",
  "Health & wellness",
  "Education",
  "Auto",
  "Agencies",
];

export default function Landing() {
  const { navigate, target } = usePrimaryCta();

  return (
    <MarketingShell
      variant="product"
      title="Flywheel — from first message to a booked deal"
      description="Flywheel qualifies, books, and follows up with every inbound lead — on any business, without a custom build. 7-day trial, $199/mo."
    >
      <section className="max-w-6xl mx-auto px-6 pt-16 md:pt-24 pb-16 grid md:grid-cols-2 gap-12 items-center">
        <div>
          <div
            className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full mb-6"
            style={{ backgroundColor: "#F5E7D6", color: "#B87333" }}
          >
            <Zap size={12} /> Any business. No custom setup.
          </div>
          <h1 className="text-4xl md:text-5xl leading-[1.08] mb-5" style={{ fontFamily: MARKETING_DISPLAY, fontWeight: 600 }}>
            From first message to a booked deal.
          </h1>
          <p className="text-base text-[#6B6459] leading-relaxed mb-6 max-w-md">
            When someone already reached out and you cannot answer them now, Flywheel carries that person to a booked deal — qualifies, books or quotes, follows up — without a custom build.
          </p>
          {salesWidgetConfigured() && (
            <p className="text-sm mb-6 max-w-md" style={{ color: "#B87333" }}>
              This site is Flywheel's first customer. The chat in the corner is the live engine, not a mock — same cycle you'd run on your own site.
            </p>
          )}
          <div className="mb-8">
            <DealCycle />
          </div>
          <div className="flex flex-wrap items-center gap-3 mb-6">
            <button
              onClick={() => navigate(target)}
              className="text-sm font-bold uppercase tracking-wide px-5 py-3 rounded flex items-center gap-2"
              style={{ backgroundColor: "#D97B29", color: "#1C1206" }}
            >
              Start 7-day free trial <ArrowRight size={15} />
            </button>
            <a href="#how" className="text-sm font-medium px-5 py-3 rounded-lg border border-[#E7E5DE] bg-white">
              See the cycle
            </a>
          </div>
          <p className="text-xs text-[#9C9488]">$199/mo after trial · card on file, no charge until day 8 · cancel anytime</p>
        </div>
        <div className="flex justify-center md:justify-end">
          <ChatBubble />
        </div>
      </section>

      <section className="border-y border-[#E7E5DE] bg-white">
        <div className="max-w-6xl mx-auto px-6 py-5 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm text-[#6B6459]">
          {INDUSTRIES.map((name) => (
            <span key={name}>{name}</span>
          ))}
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-6 py-16 md:py-20">
        <span className="text-xs font-medium text-[#B87333] uppercase tracking-wide">The job we get hired for</span>
        <h2 className="text-3xl mt-2 mb-8" style={{ fontFamily: MARKETING_DISPLAY, fontWeight: 600 }}>
          People don't hire a chatbot. They hire a finished next step.
        </h2>
        <div className="grid md:grid-cols-3 gap-5">
          <div className="bg-white rounded-2xl border border-[#E7E5DE] p-6">
            <p className="text-xs uppercase tracking-wide text-[#9C9488] mb-2">When</p>
            <p className="text-sm font-semibold mb-3">An inquiry lands while you are with a customer, in court, or off the clock</p>
            <p className="text-sm text-[#6B6459] leading-relaxed">You want that person carried to a booked deal so the money you already spent to get them is not sitting in voicemail.</p>
          </div>
          <div className="bg-white rounded-2xl border border-[#E7E5DE] p-6">
            <p className="text-xs uppercase tracking-wide text-[#9C9488] mb-2">Instead of</p>
            <p className="text-sm font-semibold mb-3">Voicemail, a $55–80k intake hire, or a chat that only captures a name</p>
            <p className="text-sm text-[#6B6459] leading-relaxed">Those are the old solutions to the same job. Flywheel keeps going through qualification, booking, and follow-up.</p>
          </div>
          <div className="bg-white rounded-2xl border border-[#E7E5DE] p-6">
            <p className="text-xs uppercase tracking-wide text-[#9C9488] mb-2">So that</p>
            <p className="text-sm font-semibold mb-3">One silent lead does not undo a $199 month — or a $649 inquiry</p>
            <p className="text-sm text-[#6B6459] leading-relaxed">Most people do not convert on the first reply. The engine follows up on a schedule you approve, then hands off when the script says so.</p>
          </div>
        </div>
      </section>

      <section id="how" className="max-w-6xl mx-auto px-6 py-20 md:py-28">
        <div className="max-w-lg mb-14">
          <span className="text-xs font-medium text-[#B87333] uppercase tracking-wide">How it works</span>
          <h2 className="text-3xl mt-2" style={{ fontFamily: MARKETING_DISPLAY, fontWeight: 600 }}>
            One path from inquiry to deal
          </h2>
          <p className="text-sm text-[#6B6459] mt-3 leading-relaxed">
            This is not a contact-capture widget. The engine keeps going until the lead is booked, won, lost — or you take over.
          </p>
        </div>
        <div className="grid md:grid-cols-2 gap-x-16">
          <div>
            <StepRow n="1" title="Someone writes in" body="Website chat today. The engine picks up the thread the moment it arrives — no one waiting on voicemail." />
            <StepRow n="2" title="It qualifies against your rules" body="Your services, questions, area, and urgency. Same questions, every time. No industry-specific rebuild." />
            <StepRow n="3" title="It books, quotes, or asks you" body="Clear cases move. Anything outside the script escalates in plain language — it never improvises a promise." last />
          </div>
          <div className="mt-2 md:mt-[52px]">
            <StepRow n="4" title="It follows up" body="People rarely buy on the first reply. If they go quiet after a quote or a booking, the cycle keeps turning until they convert, decline, or you step in." />
            <StepRow n="5" title="Every step stays on the record" body="Open any case and see the exact trigger, decision, and reply. Nothing happens off the record." last />
          </div>
        </div>
      </section>

      <section id="features" className="max-w-6xl mx-auto px-6 pb-20 md:pb-28">
        <div className="grid md:grid-cols-3 gap-5">
          <FeatureCard
            icon={MessageSquare}
            title="Answers in your voice"
            body="Tone and questions come from your Business DNA — customers get a consistent reply, not a generic chatbot."
          />
          <FeatureCard
            icon={Workflow}
            title="Runs your process"
            body="Services, qualification, booking, follow-up, and handoff are encoded once. Adaptive to the business — not a custom project per client."
          />
          <FeatureCard
            icon={ShieldCheck}
            title="Escalates instead of guessing"
            body="When something falls outside your rules, it stops and asks you. AI only rewrites wording you already approved."
          />
        </div>
      </section>

      <section id="pricing" className="bg-white border-y border-[#E7E5DE]">
        <div className="max-w-6xl mx-auto px-6 py-20 md:py-24">
          <div className="max-w-lg mb-10">
            <span className="text-xs font-medium text-[#B87333] uppercase tracking-wide">Pricing</span>
            <h2 className="text-3xl mt-2" style={{ fontFamily: MARKETING_DISPLAY, fontWeight: 600 }}>
              Start on Starter. Upgrade when you need the extras.
            </h2>
          </div>
          <div className="grid md:grid-cols-2 gap-5 max-w-3xl">
            <div className="rounded-2xl border-2 p-7" style={{ borderColor: "#D97B29", backgroundColor: "#FFF9F2" }}>
              <div className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "#D97B29" }}>
                Most new accounts
              </div>
              <div className="flex items-baseline justify-between mb-2">
                <span className="font-semibold" style={{ fontFamily: MARKETING_DISPLAY }}>Starter</span>
                <span className="text-3xl" style={{ fontFamily: MARKETING_DISPLAY, fontWeight: 600 }}>
                  $199<span className="text-sm text-[#6B6459] font-normal">/mo</span>
                </span>
              </div>
              <p className="text-sm text-[#6B6459] mb-5">7-day trial. The full inquiry-to-deal cycle for one business.</p>
              <ul className="flex flex-col gap-2.5 mb-7 text-sm">
                {[
                  "Website chat, qualification, booking, follow-up",
                  "Business DNA you set yourself — about 20 minutes",
                  "Complete audit trail",
                  "Human handoff when your rules say so",
                ].map((t) => (
                  <li key={t} className="flex items-start gap-2.5">
                    <Check size={16} className="mt-0.5 shrink-0" color="#1E7B52" /> {t}
                  </li>
                ))}
              </ul>
              <button
                onClick={() => navigate(target)}
                className="w-full text-sm font-bold uppercase tracking-wide px-5 py-3 rounded"
                style={{ backgroundColor: "#D97B29", color: "#1C1206" }}
              >
                Start free trial
              </button>
            </div>
            <div className="rounded-2xl border border-[#E7E5DE] p-7 bg-[#F5F1EA]">
              <div className="text-xs font-semibold uppercase tracking-wide text-[#6B6459] mb-2">Optional</div>
              <div className="flex items-baseline justify-between mb-2">
                <span className="font-semibold" style={{ fontFamily: MARKETING_DISPLAY }}>Pro</span>
                <span className="text-3xl" style={{ fontFamily: MARKETING_DISPLAY, fontWeight: 600 }}>
                  $499<span className="text-sm text-[#6B6459] font-normal">/mo</span>
                </span>
              </div>
              <p className="text-sm text-[#6B6459] mb-5">
                Same engine as Starter, plus priority support and early access to upcoming team features. Multi-staff routing is not live yet — don't buy Pro for that today.
              </p>
              <p className="text-xs text-[#9C9488]">You can stay on Starter. Most businesses should.</p>
            </div>
          </div>
        </div>
      </section>

      <section id="trust" className="max-w-6xl mx-auto px-6 py-20 md:py-24 grid md:grid-cols-2 gap-12 items-center">
        <div>
          <span className="text-xs font-medium text-[#B87333] uppercase tracking-wide">Trust & audit</span>
          <h2 className="text-3xl mt-2 mb-5" style={{ fontFamily: MARKETING_DISPLAY, fontWeight: 600 }}>
            Nothing the engine does is invisible
          </h2>
          <ul className="flex flex-col gap-3.5">
            {[
              "Every trigger, decision, and action is written to an append-only history",
              "AI drafts wording — it never bypasses your workflow or risk rules",
              "You can trace any booking, quote, or reply back to the exact step that produced it",
            ].map((t) => (
              <li key={t} className="flex items-start gap-2.5 text-sm text-[#151515]">
                <Check size={16} className="mt-0.5 shrink-0" color="#1E7B52" /> {t}
              </li>
            ))}
          </ul>
        </div>
        <div className="bg-white rounded-2xl border border-[#E7E5DE] p-5">
          <div className="text-xs font-medium text-[#9C9488] mb-3" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>
            CS-1042 · audit trail
          </div>
          <div className="flex flex-col gap-2.5 text-sm">
            {[
              ["09:41:02", "New", "Inbound web chat received"],
              ["09:41:03", "Context", "Matched existing lead by email"],
              ["09:41:04", "Decision", "Missing required field: timeline"],
              ["09:41:04", "Action", "Sent clarifying question"],
              ["09:44:18", "Booked", "Thursday 3:00pm confirmed"],
            ].map(([time, stage, desc]) => (
              <div key={time + stage} className="flex gap-3">
                <span className="text-[#9C9488] shrink-0" style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 12 }}>
                  {time}
                </span>
                <span className="font-medium shrink-0 w-16">{stage}</span>
                <span className="text-[#6B6459]">{desc}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="faq" className="bg-white border-y border-[#E7E5DE]">
        <div className="max-w-2xl mx-auto px-6 py-16 md:py-20">
          <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "#B87333" }}>
            FAQ
          </span>
          <h2 className="text-2xl md:text-3xl mt-2 mb-6" style={{ fontFamily: MARKETING_DISPLAY, fontWeight: 600 }}>
            Before you start
          </h2>
          <FaqItem
            q="Does this work for my kind of business?"
            a="Yes — there is no industry switch in the product. You describe services, questions, and who you can serve. The same engine runs a consultancy, a shop, or a practice. Solo attorneys in California and New York have a dedicated page because that's our first outbound wave, not because the product is legal-only."
          />
          <FaqItem
            q="Do you generate new leads for me?"
            a="No. Flywheel starts when someone has already reached out — a chat on your site today. It carries that person to a booked deal. Lead generation is a separate product, later."
          />
          <FaqItem
            q="How long does setup take?"
            a="About 20 minutes: business basics, services, area, questions, and when to hand off to you. Then paste one snippet on your website."
          />
          <FaqItem
            q="Can the AI promise something I wouldn't?"
            a="It only rewrites wording inside the script you approve. If a request falls outside that script, it escalates to you instead of inventing an answer."
          />
          <FaqItem
            q="Why follow up instead of stopping after the first reply?"
            a="Most people do not convert on the first message. Flywheel follows up on a schedule you approve — the same cycle that would otherwise die in an inbox — then stops when they book, decline, or you take over."
          />
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-6 py-20 md:py-28 text-center">
        <h2 className="text-3xl md:text-4xl mb-4" style={{ fontFamily: MARKETING_DISPLAY, fontWeight: 600 }}>
          Someone already wrote in. Don't leave them waiting.
        </h2>
        <p className="text-[#6B6459] mb-8 max-w-md mx-auto">
          Set Business DNA in minutes. Put the widget on your site. Watch the first conversation hit the dashboard.
        </p>
        <button
          onClick={() => navigate(target)}
          className="text-sm font-bold uppercase tracking-wide px-6 py-3.5 rounded inline-flex items-center gap-2"
          style={{ backgroundColor: "#D97B29", color: "#1C1206" }}
        >
          Start 7-day free trial <ArrowRight size={15} />
        </button>
      </section>
    </MarketingShell>
  );
}
