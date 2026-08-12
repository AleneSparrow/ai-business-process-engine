import { useState, type ComponentType } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight, ArrowLeft, Check, Plus, X, Building2, Wrench, MapPin,
  MessageCircleQuestion, ShieldAlert, Sparkles,
} from "lucide-react";
import { useAuth, describeError } from "../auth/AuthContext";
import { api, type OnboardingServicePayload } from "../api/client";
import { Field, inputCls, ToneOption } from "../components/Shared";

const OB_STEPS: { key: string; label: string; icon: ComponentType<{ size?: number }> }[] = [
  { key: "basics", label: "Business", icon: Building2 },
  { key: "services", label: "Services", icon: Wrench },
  { key: "area", label: "Service area", icon: MapPin },
  { key: "questions", label: "Questions", icon: MessageCircleQuestion },
  { key: "escalation", label: "Escalation", icon: ShieldAlert },
  { key: "review", label: "Review", icon: Sparkles },
];

function ProgressRail({ current }: { current: number }) {
  return (
    <div className="flex flex-col gap-0.5">
      {OB_STEPS.map((s, i) => {
        const done = i < current;
        const active = i === current;
        const Icon = s.icon;
        return (
          <div key={s.key} className="flex items-start gap-3">
            <div className="flex flex-col items-center">
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 transition-colors"
                style={{ backgroundColor: done ? "#1E7B52" : active ? "#171A21" : "#F1F1EF", color: done || active ? "#fff" : "#9AA1AC" }}
              >
                {done ? <Check size={14} /> : <Icon size={14} />}
              </div>
              {i < OB_STEPS.length - 1 && (
                <div className="w-px flex-1 min-h-[22px]" style={{ backgroundColor: done ? "#1E7B52" : "#E7E5DE" }} />
              )}
            </div>
            <div className="pt-1.5 pb-4">
              <div className="text-sm" style={{ color: active || done ? "#171A21" : "#9AA1AC", fontWeight: active ? 600 : 500 }}>
                {s.label}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

const TONE_OPTIONS: [string, string][] = [
  ["Friendly & direct", "Warm, no filler"],
  ["Formal & precise", "Professional tone"],
  ["Casual & brief", "Short, plain texts"],
];

const ESCALATION_OPTIONS: [string, string, string][] = [
  ["outsideArea", "Lead is outside your service area", "Never auto-books a job it can't confirm you can reach."],
  ["priceObjection", "Customer pushes back on price", "Pricing conversations route to you by default. (Detecting this automatically is on the roadmap — for now every case routes to human review.)"],
  ["angryTone", "Message reads as frustrated or urgent", "Tone signals that call for a person, not a script. (Also on the roadmap — every case currently routes to human review by default.)"],
];

export default function Onboarding() {
  const navigate = useNavigate();
  const { user, setUser, token } = useAuth();

  const [step, setStep] = useState(0);
  const [business, setBusiness] = useState({ name: "", industry: "Home services", tone: "Friendly & direct" });
  const [services, setServices] = useState<string[]>(["Furnace diagnostic", "AC repair", "Drain cleaning"]);
  const [newService, setNewService] = useState("");
  const [radius, setRadius] = useState(25);
  const [zips, setZips] = useState("60601, 60602, 60603");
  const [questions, setQuestions] = useState<Record<string, string[]>>({
    "Furnace diagnostic": ["Unit age?", "Making unusual noise or smell?"],
  });
  const [escalation, setEscalation] = useState({ outsideArea: true, priceObjection: true, angryTone: true });
  const [launched, setLaunched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const next = () => setStep((s) => Math.min(s + 1, OB_STEPS.length - 1));
  const back = () => setStep((s) => Math.max(s - 1, 0));
  const addService = () => {
    if (newService.trim()) {
      setServices([...services, newService.trim()]);
      setNewService("");
    }
  };

  async function launch() {
    if (!token) return;
    setError(null);
    setSubmitting(true);
    try {
      const servicePayloads: OnboardingServicePayload[] = services.map((name) => ({
        name,
        questions: (questions[name] ?? []).map((q) => q.trim()).filter(Boolean),
      }));
      const zipCodes = zips
        .split(",")
        .map((z) => z.trim())
        .filter(Boolean);

      const created = await api.createBusiness(token, {
        business_name: business.name.trim() || "Untitled business",
        industry: business.industry,
        tone: business.tone,
        services: servicePayloads,
        service_zip_codes: zipCodes,
        enforce_service_area: true,
      });

      if (user) {
        setUser({ ...user, business_id: created.business_id });
      }
      setLaunched(true);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{ backgroundColor: "#F7F6F2", fontFamily: "'Inter', sans-serif", color: "#171A21" }} className="min-h-screen w-full">
      <header className="border-b border-[#E7E5DE] bg-white">
        <div className="max-w-5xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center text-white text-xs font-bold"
              style={{ backgroundColor: "#3A3EA6", fontFamily: "'Space Grotesk', sans-serif" }}
            >
              A
            </div>
            <span className="font-semibold text-sm" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              Setting up your Business DNA
            </span>
          </div>
          <span className="text-xs text-[#9AA1AC]" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>
            Step {step + 1} / {OB_STEPS.length}
          </span>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-6 py-10 md:py-14 grid md:grid-cols-[200px_1fr] gap-10">
        <div className="hidden md:block"><ProgressRail current={step} /></div>

        <div className="bg-white rounded-2xl border border-[#E7E5DE] p-6 md:p-8 min-h-[480px] flex flex-col">
          {!launched ? (
            <>
              <div className="flex-1 dna-fade" key={step}>
                {step === 0 && (
                  <>
                    <h2 className="text-2xl mb-1.5" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>Tell us about your business</h2>
                    <p className="text-sm text-[#6B7280] mb-7">This shapes how your engine talks to every customer.</p>
                    <Field label="Business name">
                      <input className={inputCls} placeholder="Acme Home Services" value={business.name} onChange={(e) => setBusiness({ ...business, name: e.target.value })} />
                    </Field>
                    <Field label="Industry">
                      <select className={inputCls} value={business.industry} onChange={(e) => setBusiness({ ...business, industry: e.target.value })}>
                        <option>Home services</option><option>Auto repair</option><option>Health & wellness</option><option>Professional services</option>
                      </select>
                    </Field>
                    <Field label="How should it sound to customers?">
                      <div className="grid sm:grid-cols-3 gap-2.5">
                        {TONE_OPTIONS.map(([label, desc]) => (
                          <ToneOption key={label} label={label} desc={desc} active={business.tone === label} onClick={() => setBusiness({ ...business, tone: label })} />
                        ))}
                      </div>
                    </Field>
                  </>
                )}

                {step === 1 && (
                  <>
                    <h2 className="text-2xl mb-1.5" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>What do you offer?</h2>
                    <p className="text-sm text-[#6B7280] mb-7">
                      Every service starts routed to you for review — nothing auto-books or auto-quotes until you turn that on later.
                    </p>
                    <div className="flex flex-wrap gap-2 mb-4">
                      {services.map((s) => (
                        <span key={s} className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm bg-[#F1F1EF] border border-[#E7E5DE]">
                          {s} <X size={12} className="cursor-pointer text-[#9AA1AC]" onClick={() => setServices(services.filter((x) => x !== s))} />
                        </span>
                      ))}
                    </div>
                    <div className="flex gap-2">
                      <input className={inputCls} placeholder="Add a service" value={newService} onChange={(e) => setNewService(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addService())} />
                      <button type="button" onClick={addService} className="px-4 rounded-lg text-white text-sm font-medium flex items-center gap-1.5 shrink-0" style={{ backgroundColor: "#171A21" }}>
                        <Plus size={14} /> Add
                      </button>
                    </div>
                  </>
                )}

                {step === 2 && (
                  <>
                    <h2 className="text-2xl mb-1.5" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>Where do you work?</h2>
                    <p className="text-sm text-[#6B7280] mb-7">Leads outside this area escalate to you instead of getting booked automatically.</p>
                    <Field label="Service radius" hint={`${radius} miles from your base zip code`}>
                      <input type="range" min="5" max="60" value={radius} onChange={(e) => setRadius(Number(e.target.value))} className="w-full accent-[#3A3EA6]" />
                    </Field>
                    <Field label="Known service zip codes" hint="Comma-separated — the engine matches against these first">
                      <textarea className={inputCls} rows={3} value={zips} onChange={(e) => setZips(e.target.value)} />
                    </Field>
                  </>
                )}

                {step === 3 && (
                  <>
                    <h2 className="text-2xl mb-1.5" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>What does it need to ask?</h2>
                    <p className="text-sm text-[#6B7280] mb-7">Per service, the questions your engine confirms before booking.</p>
                    {services.map((svc) => (
                      <div key={svc} className="mb-5 pb-5 border-b border-[#F0EFE9] last:border-0">
                        <div className="text-sm font-semibold mb-2.5">{svc}</div>
                        <div className="flex flex-col gap-2">
                          {(questions[svc] || ["What's the issue you're experiencing?"]).map((q, i) => (
                            <div key={i} className="flex items-center gap-2">
                              <span className="text-xs text-[#9AA1AC] w-5 shrink-0" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>{i + 1}</span>
                              <input
                                className={inputCls}
                                value={q}
                                onChange={(e) => {
                                  const qs = [...(questions[svc] || [])];
                                  qs[i] = e.target.value;
                                  setQuestions({ ...questions, [svc]: qs });
                                }}
                              />
                            </div>
                          ))}
                          <button
                            type="button"
                            className="text-xs font-medium text-[#3A3EA6] flex items-center gap-1 mt-0.5 ml-7"
                            onClick={() => setQuestions({ ...questions, [svc]: [...(questions[svc] || []), ""] })}
                          >
                            <Plus size={12} /> Add question
                          </button>
                        </div>
                      </div>
                    ))}
                  </>
                )}

                {step === 4 && (
                  <>
                    <h2 className="text-2xl mb-1.5" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>When should it hand off to you?</h2>
                    <p className="text-sm text-[#6B7280] mb-7">The engine never guesses past these lines — it stops and asks.</p>
                    <div className="flex flex-col gap-3">
                      {ESCALATION_OPTIONS.map(([key, title, desc]) => (
                        <label
                          key={key}
                          className="flex items-start gap-3 p-4 rounded-xl border cursor-pointer"
                          style={{
                            borderColor: escalation[key as keyof typeof escalation] ? "#3A3EA6" : "#E7E5DE",
                            backgroundColor: escalation[key as keyof typeof escalation] ? "#EEEEF9" : "#fff",
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={escalation[key as keyof typeof escalation]}
                            onChange={() => setEscalation({ ...escalation, [key]: !escalation[key as keyof typeof escalation] })}
                            className="mt-0.5 accent-[#3A3EA6]"
                          />
                          <div>
                            <div className="text-sm font-medium">{title}</div>
                            <div className="text-xs text-[#6B7280] mt-0.5">{desc}</div>
                          </div>
                        </label>
                      ))}
                    </div>
                  </>
                )}

                {step === 5 && (
                  <>
                    <h2 className="text-2xl mb-1.5" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>Ready to go live</h2>
                    <p className="text-sm text-[#6B7280] mb-7">Here's the Business DNA your engine will run on.</p>
                    <div className="rounded-xl bg-[#F7F6F2] border border-[#E7E5DE] p-5 flex flex-col gap-4 text-sm">
                      <div className="flex justify-between"><span className="text-[#6B7280]">Business</span><span className="font-medium">{business.name || "Untitled business"} · {business.industry}</span></div>
                      <div className="flex justify-between"><span className="text-[#6B7280]">Voice</span><span className="font-medium">{business.tone}</span></div>
                      <div className="flex justify-between"><span className="text-[#6B7280]">Services</span><span className="font-medium text-right">{services.join(", ")}</span></div>
                      <div className="flex justify-between"><span className="text-[#6B7280]">Service radius</span><span className="font-medium">{radius} miles</span></div>
                      <div className="flex justify-between"><span className="text-[#6B7280]">Escalation rules</span><span className="font-medium">{Object.values(escalation).filter(Boolean).length} active</span></div>
                    </div>
                    <div className="flex items-center gap-2 mt-5 text-xs" style={{ color: "#1E7B52" }}>
                      <Check size={14} /> Every service starts on human review — nothing books or quotes itself until you turn that on.
                    </div>
                    {error && (
                      <div className="mt-4 text-sm px-3.5 py-2.5 rounded-lg" style={{ color: "#B4483A", backgroundColor: "#FBEBE9" }}>
                        {error}
                      </div>
                    )}
                  </>
                )}
              </div>

              <div className="flex items-center justify-between pt-6 mt-6 border-t border-[#F0EFE9]">
                <button onClick={back} disabled={step === 0} className="text-sm font-medium px-4 py-2.5 rounded-lg flex items-center gap-1.5 disabled:opacity-0" style={{ color: "#6B7280" }}>
                  <ArrowLeft size={14} /> Back
                </button>
                {step < OB_STEPS.length - 1 ? (
                  <button onClick={next} className="text-sm font-medium text-white px-5 py-2.5 rounded-lg flex items-center gap-1.5" style={{ backgroundColor: "#171A21" }}>
                    Continue <ArrowRight size={14} />
                  </button>
                ) : (
                  <button
                    onClick={launch}
                    disabled={submitting}
                    className="text-sm font-medium text-white px-5 py-2.5 rounded-lg flex items-center gap-1.5 disabled:opacity-60"
                    style={{ backgroundColor: "#1E7B52" }}
                  >
                    {submitting ? "Launching…" : "Launch engine"} <Sparkles size={14} />
                  </button>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-center dna-fade">
              <div className="w-12 h-12 rounded-full flex items-center justify-center mb-5" style={{ backgroundColor: "#E9F5EF" }}>
                <Check size={22} color="#1E7B52" />
              </div>
              <h2 className="text-2xl mb-2" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>
                {business.name || "Your business"} is live.
              </h2>
              <p className="text-sm text-[#6B7280] mb-7 max-w-sm">It's answering new leads right now, using exactly what you just set up.</p>
              <button
                onClick={() => navigate("/app")}
                className="text-sm font-medium text-white px-5 py-2.5 rounded-lg flex items-center gap-1.5"
                style={{ backgroundColor: "#171A21" }}
              >
                Go to dashboard <ArrowRight size={14} />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
