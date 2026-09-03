import React, { useState, useMemo } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Check,
  Plus,
  X,
  ShieldAlert,
  Sparkles,
  ArrowLeft,
} from "lucide-react";

const COLOR = {
  paper: "#F6F4EC",
  paperSoft: "#EFEBDD",
  ink: "#221F1A",
  inkSoft: "#726D62",
  inkFaint: "#A7A091",
  line: "#E1DAC6",
  indigo: "#4A3FCF",
  indigoDeep: "#372FA0",
  indigoSoft: "#ECEAFB",
  brick: "#9C4A32",
  brickSoft: "#F3E4DC",
  moss: "#3F7A5C",
  mossSoft: "#E3EDE6",
  amber: "#B07C25",
  amberSoft: "#F4EAD4",
};

const FONT = {
  display: "'Space Grotesk', sans-serif",
  body: "'Inter', sans-serif",
  mono: "'IBM Plex Mono', monospace",
};

const STAGES = ["Trigger", "Context", "Decision", "Action", "Result"];
const STAGE_FOR_STEP = [1, 1, 2, 3, 4];

const INDUSTRIES = ["Plumbing", "Cleaning", "Dental", "HVAC", "Salon", "Other"];
const CHANNELS = ["Website chat", "SMS", "WhatsApp"];

const TRIGGERS = [
  { id: "refund", label: "Asks for a refund or cancellation", desc: "Money leaving the business always goes to a person." },
  { id: "upset", label: "Sounds upset or frustrated", desc: "Tone matters more than the words here." },
  { id: "price", label: "Tries to negotiate price", desc: "Keeps quotes consistent — no AI discounts." },
  { id: "urgent", label: "Says it's an emergency", desc: "Anything time-critical skips the queue." },
];

const STEP_TITLES = [
  "The basics",
  "What you offer",
  "When to bring in a person",
  "How it sounds",
  "Review & activate",
];

export default function BusinessDNAOnboarding() {
  const [step, setStep] = useState(0);
  const [activated, setActivated] = useState(false);

  const [businessName, setBusinessName] = useState("");
  const [industry, setIndustry] = useState(null);
  const [customIndustry, setCustomIndustry] = useState("");
  const [channel, setChannel] = useState("Website chat");

  const [services, setServices] = useState([]);
  const [serviceInput, setServiceInput] = useState("");

  const [triggers, setTriggers] = useState([]);

  const [tone, setTone] = useState(60);
  const [greeting, setGreeting] = useState("");

  const industryLabel = industry === "Other" ? (customIndustry || "your trade") : industry;
  const displayName = businessName.trim() || "your business";

  const toggleTrigger = (id) =>
    setTriggers((t) => (t.includes(id) ? t.filter((x) => x !== id) : [...t, id]));

  const addService = () => {
    const v = serviceInput.trim();
    if (v && !services.includes(v)) setServices((s) => [...s, v]);
    setServiceInput("");
  };
  const removeService = (v) => setServices((s) => s.filter((x) => x !== v));

  const canContinue = useMemo(() => {
    if (step === 0) return businessName.trim().length > 0 && !!industry;
    if (step === 1) return services.length > 0;
    if (step === 2) return triggers.length > 0;
    return true;
  }, [step, businessName, industry, services, triggers]);

  const defaultGreeting = tone > 50
    ? `Hey! Thanks for reaching out to ${businessName.trim() || "us"} — what can I help with?`
    : `Hello, thank you for contacting ${businessName.trim() || "us"}. How can I help you today?`;

  const preview = useMemo(() => {
    const warm = tone > 50;
    if (step === 0) {
      return {
        customer: "Hi, do you do same-day service?",
        reply: industry
          ? `${warm ? "Yeah, we" : "Yes, we"} usually can fit in same-day ${industryLabel.toLowerCase()} work — mind sharing your address and what's going on?`
          : "Let me check on that for you — one moment.",
        confidence: industry && businessName ? 0.81 : 0.52,
      };
    }
    if (step === 1) {
      const list = services.slice(0, 2).join(" and ");
      return {
        customer: "What services do you offer?",
        reply: services.length
          ? `We handle ${list}${services.length > 2 ? `, plus ${services.length - 2} more` : ""}. Which one do you need?`
          : "Add a service on the left to see this update.",
        confidence: services.length ? Math.min(0.6 + services.length * 0.08, 0.93) : 0.4,
      };
    }
    if (step === 2) {
      const active = TRIGGERS.find((t) => triggers.includes(t.id));
      if (!active) {
        return { customer: "This is unacceptable, I want my money back.", reply: "Select at least one hand-off rule on the left.", confidence: 0.4, escalate: false };
      }
      const lines = {
        refund: "This is unacceptable, I want my money back.",
        upset: "I've called three times and no one has helped me.",
        price: "Can you do it for half that price?",
        urgent: "My basement is flooding right now!",
      };
      return {
        customer: lines[active.id],
        reply: "I hear you — let me get a teammate on this right now so it's handled properly.",
        confidence: 0.88,
        escalate: true,
      };
    }
    if (step === 3) {
      return {
        customer: "Hey, are you around today?",
        reply: greeting.trim() || defaultGreeting,
        confidence: 0.75,
      };
    }
    return {
      customer: "Hi, do you do same-day service?",
      reply: industry
        ? `${warm ? "Yeah, we" : "Yes, we"} usually can fit in same-day ${industryLabel.toLowerCase()} work — mind sharing your address and what's going on?`
        : "Configuration incomplete.",
      confidence: 0.9,
    };
  }, [step, industry, industryLabel, businessName, services, triggers, tone, greeting, defaultGreeting]);

  const activeStage = activated ? 4 : STAGE_FOR_STEP[step];

  return (
    <div style={{ background: COLOR.paper, fontFamily: FONT.body, color: COLOR.ink, minHeight: "100%" }} className="w-full">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@500&display=swap');
        .dna-fade { animation: dnaFade 0.35s ease; }
        @keyframes dnaFade { from { opacity: 0; transform: translateY(3px); } to { opacity: 1; transform: translateY(0); } }
        .dna-pulse { animation: dnaPulse 1.8s ease-in-out infinite; }
        @keyframes dnaPulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }
        input[type=range].dna-slider { -webkit-appearance: none; height: 4px; border-radius: 999px; background: ${COLOR.line}; }
        input[type=range].dna-slider::-webkit-slider-thumb { -webkit-appearance: none; width: 18px; height: 18px; border-radius: 999px; background: ${COLOR.indigo}; border: 3px solid ${COLOR.paper}; box-shadow: 0 0 0 1px ${COLOR.indigo}; cursor: pointer; margin-top: -7px; }
        input[type=range].dna-slider::-moz-range-thumb { width: 18px; height: 18px; border-radius: 999px; background: ${COLOR.indigo}; border: 3px solid ${COLOR.paper}; box-shadow: 0 0 0 1px ${COLOR.indigo}; cursor: pointer; }
      `}</style>

      {/* Top bar */}
      <div style={{ borderBottom: `1px solid ${COLOR.line}` }} className="px-6 md:px-10 py-4 flex items-center justify-between">
        <button className="flex items-center gap-2 text-sm" style={{ color: COLOR.inkSoft, fontFamily: FONT.body }}>
          <ArrowLeft size={15} /> Dashboard
        </button>
        <div style={{ fontFamily: FONT.mono, fontSize: 12, color: COLOR.inkFaint, letterSpacing: 0.3 }}>
          BUSINESS DNA · SETUP
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 md:px-10 py-10 grid grid-cols-1 md:grid-cols-5 gap-10">
        {/* LEFT: wizard */}
        <div className="md:col-span-3 order-2 md:order-1">
          {/* Stepper */}
          <div className="flex items-center gap-2 mb-8">
            {STEP_TITLES.map((t, i) => (
              <div key={t} className="flex items-center gap-2 flex-1">
                <div
                  className="flex items-center justify-center rounded-full flex-shrink-0"
                  style={{
                    width: 26, height: 26,
                    fontFamily: FONT.mono, fontSize: 11,
                    background: i < step || activated ? COLOR.indigo : i === step ? COLOR.indigoSoft : "transparent",
                    color: i < step || activated ? "#fff" : i === step ? COLOR.indigoDeep : COLOR.inkFaint,
                    border: i === step ? `1.5px solid ${COLOR.indigo}` : `1.5px solid ${COLOR.line}`,
                  }}
                >
                  {i < step || activated ? <Check size={13} /> : i + 1}
                </div>
                {i < STEP_TITLES.length - 1 && (
                  <div style={{ height: 1.5, flex: 1, background: i < step || activated ? COLOR.indigo : COLOR.line }} />
                )}
              </div>
            ))}
          </div>

          {!activated ? (
            <>
              <div style={{ fontFamily: FONT.mono, fontSize: 12, color: COLOR.indigoDeep, marginBottom: 6 }}>
                STEP {step + 1} OF {STEP_TITLES.length}
              </div>
              <h1 style={{ fontFamily: FONT.display, fontSize: 30, fontWeight: 600, marginBottom: 28 }}>
                {STEP_TITLES[step]}
              </h1>

              <div key={step} className="dna-fade">
                {step === 0 && (
                  <div className="space-y-6">
                    <div>
                      <label className="block text-sm mb-2" style={{ color: COLOR.inkSoft }}>What's your business called?</label>
                      <input
                        value={businessName}
                        onChange={(e) => setBusinessName(e.target.value)}
                        placeholder="e.g. Harbor Street Plumbing"
                        className="w-full px-4 py-3 rounded-lg text-sm outline-none"
                        style={{ background: "#fff", border: `1px solid ${COLOR.line}`, fontFamily: FONT.body }}
                      />
                    </div>
                    <div>
                      <label className="block text-sm mb-2" style={{ color: COLOR.inkSoft }}>What trade are you in?</label>
                      <div className="flex flex-wrap gap-2">
                        {INDUSTRIES.map((opt) => (
                          <button
                            key={opt}
                            onClick={() => setIndustry(opt)}
                            className="px-3.5 py-2 rounded-full text-sm"
                            style={{
                              border: `1px solid ${industry === opt ? COLOR.indigo : COLOR.line}`,
                              background: industry === opt ? COLOR.indigoSoft : "#fff",
                              color: industry === opt ? COLOR.indigoDeep : COLOR.ink,
                            }}
                          >
                            {opt}
                          </button>
                        ))}
                      </div>
                      {industry === "Other" && (
                        <input
                          value={customIndustry}
                          onChange={(e) => setCustomIndustry(e.target.value)}
                          placeholder="Tell us what you do"
                          className="mt-3 w-full px-4 py-3 rounded-lg text-sm outline-none"
                          style={{ background: "#fff", border: `1px solid ${COLOR.line}` }}
                        />
                      )}
                    </div>
                    <div>
                      <label className="block text-sm mb-2" style={{ color: COLOR.inkSoft }}>Where do customers reach you?</label>
                      <div className="flex flex-wrap gap-2">
                        {CHANNELS.map((c) => (
                          <button
                            key={c}
                            onClick={() => setChannel(c)}
                            className="px-3.5 py-2 rounded-full text-sm"
                            style={{
                              border: `1px solid ${channel === c ? COLOR.indigo : COLOR.line}`,
                              background: channel === c ? COLOR.indigoSoft : "#fff",
                              color: channel === c ? COLOR.indigoDeep : COLOR.ink,
                            }}
                          >
                            {c}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {step === 1 && (
                  <div className="space-y-4">
                    <label className="block text-sm" style={{ color: COLOR.inkSoft }}>
                      List what you do — one at a time. This is what it'll offer and quote from.
                    </label>
                    <div className="flex gap-2">
                      <input
                        value={serviceInput}
                        onChange={(e) => setServiceInput(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && addService()}
                        placeholder="e.g. drain cleaning"
                        className="flex-1 px-4 py-3 rounded-lg text-sm outline-none"
                        style={{ background: "#fff", border: `1px solid ${COLOR.line}` }}
                      />
                      <button
                        onClick={addService}
                        className="px-4 rounded-lg flex items-center gap-1 text-sm"
                        style={{ background: COLOR.indigo, color: "#fff" }}
                      >
                        <Plus size={15} /> Add
                      </button>
                    </div>
                    <div className="flex flex-wrap gap-2 pt-1">
                      {services.map((s) => (
                        <span
                          key={s}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm"
                          style={{ background: COLOR.paperSoft, border: `1px solid ${COLOR.line}` }}
                        >
                          {s}
                          <X size={12} style={{ cursor: "pointer", color: COLOR.inkFaint }} onClick={() => removeService(s)} />
                        </span>
                      ))}
                      {services.length === 0 && (
                        <span className="text-sm" style={{ color: COLOR.inkFaint }}>Nothing added yet.</span>
                      )}
                    </div>
                  </div>
                )}

                {step === 2 && (
                  <div className="space-y-3">
                    <label className="block text-sm mb-1" style={{ color: COLOR.inkSoft }}>
                      Pick what should always go to a person, not the AI.
                    </label>
                    {TRIGGERS.map((t) => (
                      <button
                        key={t.id}
                        onClick={() => toggleTrigger(t.id)}
                        className="w-full flex items-start gap-3 p-4 rounded-lg text-left"
                        style={{
                          background: triggers.includes(t.id) ? COLOR.brickSoft : "#fff",
                          border: `1px solid ${triggers.includes(t.id) ? COLOR.brick : COLOR.line}`,
                        }}
                      >
                        <div
                          className="mt-0.5 flex items-center justify-center rounded flex-shrink-0"
                          style={{
                            width: 18, height: 18,
                            background: triggers.includes(t.id) ? COLOR.brick : "#fff",
                            border: `1px solid ${triggers.includes(t.id) ? COLOR.brick : COLOR.line}`,
                          }}
                        >
                          {triggers.includes(t.id) && <Check size={12} color="#fff" />}
                        </div>
                        <div>
                          <div className="text-sm font-medium">{t.label}</div>
                          <div className="text-sm" style={{ color: COLOR.inkSoft }}>{t.desc}</div>
                        </div>
                      </button>
                    ))}
                  </div>
                )}

                {step === 3 && (
                  <div className="space-y-8">
                    <div>
                      <label className="block text-sm mb-3" style={{ color: COLOR.inkSoft }}>
                        Straightforward <span style={{ float: "right" }}>Warm</span>
                      </label>
                      <input
                        type="range" min="0" max="100" value={tone}
                        onChange={(e) => setTone(Number(e.target.value))}
                        className="dna-slider w-full"
                      />
                    </div>
                    <div>
                      <label className="block text-sm mb-2" style={{ color: COLOR.inkSoft }}>Opening line</label>
                      <textarea
                        value={greeting}
                        onChange={(e) => setGreeting(e.target.value)}
                        placeholder={defaultGreeting}
                        rows={3}
                        className="w-full px-4 py-3 rounded-lg text-sm outline-none resize-none"
                        style={{ background: "#fff", border: `1px solid ${COLOR.line}` }}
                      />
                      <button
                        onClick={() => setGreeting(defaultGreeting)}
                        className="mt-2 flex items-center gap-1.5 text-sm"
                        style={{ color: COLOR.indigoDeep }}
                      >
                        <Sparkles size={13} /> Suggest a line
                      </button>
                    </div>
                  </div>
                )}

                {step === 4 && (
                  <div className="space-y-4">
                    <SummaryRow label="Business" value={`${displayName} · ${industryLabel || "—"}`} />
                    <SummaryRow label="Channel" value={channel} />
                    <SummaryRow label="Services" value={services.join(", ") || "—"} />
                    <SummaryRow
                      label="Hands off to a person when"
                      value={triggers.map((id) => TRIGGERS.find((t) => t.id === id)?.label).join("; ") || "—"}
                    />
                    <SummaryRow label="Tone" value={tone > 50 ? "Warm" : "Straightforward"} />
                    <button
                      onClick={() => setActivated(true)}
                      className="w-full mt-4 py-3.5 rounded-lg text-sm font-medium"
                      style={{ background: COLOR.indigo, color: "#fff" }}
                    >
                      Activate Business DNA
                    </button>
                  </div>
                )}
              </div>

              {step < 4 && (
                <div className="flex items-center justify-between mt-10">
                  <button
                    onClick={() => setStep((s) => Math.max(0, s - 1))}
                    disabled={step === 0}
                    className="flex items-center gap-1.5 text-sm px-4 py-2.5 rounded-lg"
                    style={{ color: step === 0 ? COLOR.inkFaint : COLOR.ink, border: `1px solid ${COLOR.line}`, opacity: step === 0 ? 0.5 : 1 }}
                  >
                    <ChevronLeft size={15} /> Back
                  </button>
                  <button
                    onClick={() => canContinue && setStep((s) => Math.min(4, s + 1))}
                    disabled={!canContinue}
                    className="flex items-center gap-1.5 text-sm px-5 py-2.5 rounded-lg font-medium"
                    style={{ background: canContinue ? COLOR.indigo : COLOR.line, color: canContinue ? "#fff" : COLOR.inkFaint }}
                  >
                    Continue <ChevronRight size={15} />
                  </button>
                </div>
              )}
            </>
          ) : (
            <div className="dna-fade">
              <div
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm mb-5"
                style={{ background: COLOR.mossSoft, color: COLOR.moss }}
              >
                <span style={{ width: 6, height: 6, borderRadius: 999, background: COLOR.moss }} />
                Live
              </div>
              <h1 style={{ fontFamily: FONT.display, fontSize: 30, fontWeight: 600, marginBottom: 12 }}>
                {displayName} is set up.
              </h1>
              <p className="text-sm mb-8" style={{ color: COLOR.inkSoft, maxWidth: 440 }}>
                It's now replying on {channel.toLowerCase()} using what you just told it — and handing off
                to a person the moment one of your {triggers.length} rules fires. You can change any of this later.
              </p>
              <button
                onClick={() => setActivated(false)}
                className="text-sm px-4 py-2.5 rounded-lg"
                style={{ border: `1px solid ${COLOR.line}` }}
              >
                Edit setup
              </button>
            </div>
          )}
        </div>

        {/* RIGHT: live preview */}
        <div className="md:col-span-2 order-1 md:order-2">
          <div className="sticky top-8">
            <div className="flex items-center justify-between mb-3">
              <span style={{ fontFamily: FONT.mono, fontSize: 12, color: COLOR.inkFaint, letterSpacing: 0.3 }}>
                HOW IT RESPONDS RIGHT NOW
              </span>
              <span className="flex items-center gap-1.5 text-xs dna-pulse" style={{ color: COLOR.indigoDeep }}>
                <span style={{ width: 5, height: 5, borderRadius: 999, background: COLOR.indigo }} />
                live
              </span>
            </div>

            <div className="rounded-2xl p-5" style={{ background: "#fff", border: `1px solid ${COLOR.line}` }}>
              <div key={step + preview.customer} className="dna-fade space-y-3">
                <div className="flex justify-end">
                  <div
                    className="px-3.5 py-2.5 rounded-2xl rounded-br-sm text-sm max-w-[85%]"
                    style={{ background: COLOR.paperSoft }}
                  >
                    {preview.customer}
                  </div>
                </div>
                <div className="flex justify-start">
                  <div
                    className="px-3.5 py-2.5 rounded-2xl rounded-bl-sm text-sm max-w-[85%]"
                    style={{ background: COLOR.indigo, color: "#fff" }}
                  >
                    {preview.reply}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2 mt-4 pt-4" style={{ borderTop: `1px solid ${COLOR.line}` }}>
                {preview.escalate ? (
                  <span className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full" style={{ background: COLOR.brickSoft, color: COLOR.brick }}>
                    <ShieldAlert size={12} /> Escalated to a person
                  </span>
                ) : (
                  <span className="text-xs px-2.5 py-1 rounded-full" style={{ background: COLOR.amberSoft, color: COLOR.amber, fontFamily: FONT.mono }}>
                    confidence {preview.confidence.toFixed(2)}
                  </span>
                )}
              </div>
            </div>

            {/* engine stage breadcrumb */}
            <div className="mt-6 px-1">
              <div className="flex items-center justify-between mb-2">
                {STAGES.map((s, i) => (
                  <span key={s} style={{ fontFamily: FONT.mono, fontSize: 10, color: i === activeStage ? COLOR.indigoDeep : COLOR.inkFaint }}>
                    {s}
                  </span>
                ))}
              </div>
              <div className="flex items-center gap-1.5">
                {STAGES.map((s, i) => (
                  <div
                    key={s}
                    className="flex-1 rounded-full"
                    style={{
                      height: 4,
                      background: i < activeStage ? COLOR.moss : i === activeStage ? COLOR.indigo : COLOR.line,
                    }}
                  />
                ))}
              </div>
              <p className="text-xs mt-3" style={{ color: COLOR.inkFaint }}>
                This step is shaping the <b style={{ color: COLOR.inkSoft }}>{STAGES[activeStage]}</b> stage of the engine.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function SummaryRow({ label, value }) {
  return (
    <div className="flex items-start justify-between gap-6 py-3" style={{ borderBottom: `1px solid ${COLOR.line}` }}>
      <span className="text-sm flex-shrink-0" style={{ color: COLOR.inkSoft, width: 180 }}>{label}</span>
      <span className="text-sm text-right">{value}</span>
    </div>
  );
}
