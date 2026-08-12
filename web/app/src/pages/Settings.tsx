import { useMemo, useState } from "react";
import { Check, Plus, RotateCcw, X } from "lucide-react";
import { Sidebar } from "../components/Sidebar";
import { Field, inputCls, ToneOption, PreviewBanner } from "../components/Shared";

const SETTINGS_TABS = [
  { key: "business", label: "Business" },
  { key: "services", label: "Services" },
  { key: "area", label: "Service area" },
  { key: "questions", label: "Questions" },
  { key: "escalation", label: "Escalation" },
] as const;

type TabKey = (typeof SETTINGS_TABS)[number]["key"];

type SettingsState = {
  name: string;
  industry: string;
  tone: string;
  services: string[];
  radius: number;
  zips: string;
  questions: Record<string, string[]>;
  escalation: { outsideArea: boolean; priceObjection: boolean; angryTone: boolean };
};

/**
 * Preview data mirroring the Business DNA shape the onboarding wizard actually
 * submits. Editing here is illustrative only — there's no settings-update API yet,
 * so "Save changes" doesn't persist. Use Onboarding to create the real configuration.
 */
const SETTINGS_INITIAL: SettingsState = {
  name: "Acme Home Services",
  industry: "Home services",
  tone: "Friendly & direct",
  services: ["Furnace diagnostic", "AC repair", "Drain cleaning"],
  radius: 25,
  zips: "60601, 60602, 60603",
  questions: {
    "Furnace diagnostic": ["Unit age?", "Making unusual noise or smell?"],
    "AC repair": ["Is the unit still running, just poorly, or fully off?"],
    "Drain cleaning": ["Which drain — kitchen, bathroom, or main line?"],
  },
  escalation: { outsideArea: true, priceObjection: true, angryTone: true },
};

const TONE_OPTIONS: [string, string][] = [
  ["Friendly & direct", "Warm, no filler"],
  ["Formal & precise", "Professional tone"],
  ["Casual & brief", "Short, plain texts"],
];

const ESCALATION_OPTIONS: [keyof SettingsState["escalation"], string, string][] = [
  ["outsideArea", "Lead is outside your service area", "Never auto-books a job it can't confirm you can reach."],
  ["priceObjection", "Customer pushes back on price", "Pricing conversations route to you by default."],
  ["angryTone", "Message reads as frustrated or urgent", "Tone signals that call for a person, not a script."],
];

export default function Settings() {
  const [tab, setTab] = useState<TabKey>("business");
  const [state, setState] = useState<SettingsState>(SETTINGS_INITIAL);
  const [newService, setNewService] = useState("");
  const [savedAt, setSavedAt] = useState("2 days ago");
  const dirty = useMemo(() => JSON.stringify(state) !== JSON.stringify(SETTINGS_INITIAL), [state]);

  const addService = () => {
    const v = newService.trim();
    if (v && !state.services.includes(v)) {
      setState({ ...state, services: [...state.services, v] });
      setNewService("");
    }
  };
  const removeService = (s: string) => setState({ ...state, services: state.services.filter((x) => x !== s) });
  const save = () => setSavedAt("just now");
  const discard = () => setState(SETTINGS_INITIAL);

  return (
    <div className="min-h-screen w-full flex" style={{ backgroundColor: "#F7F6F2", fontFamily: "'Inter', sans-serif", color: "#171A21" }}>
      <Sidebar />
      <main className="flex-1 min-w-0 flex flex-col">
        <PreviewBanner text="Preview data — this doesn't reflect the business you just created. Editing here won't save yet." />
        <header className="flex items-center justify-between px-6 md:px-8 py-4 border-b border-[#E7E5DE]">
          <div>
            <h1 className="text-xl" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>Business DNA</h1>
            <p className="text-sm text-[#6B7280] mt-0.5" style={{ fontFamily: dirty ? "'Inter', sans-serif" : "'IBM Plex Mono', monospace" }}>
              {dirty ? "Unsaved changes" : `Last updated ${savedAt}`}
            </p>
          </div>
          {!dirty && (
            <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full" style={{ color: "#1E7B52", backgroundColor: "#E9F5EF" }}>
              <Check size={12} /> Live
            </span>
          )}
        </header>

        <div className="max-w-3xl px-6 md:px-8 py-8 w-full">
          <div className="flex items-center gap-1 mb-8 border-b border-[#E7E5DE] overflow-x-auto">
            {SETTINGS_TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className="px-3.5 py-2.5 text-sm whitespace-nowrap relative -mb-px"
                style={{ color: tab === t.key ? "#171A21" : "#9AA1AC", fontWeight: tab === t.key ? 600 : 500 }}
              >
                {t.label}
                {tab === t.key && <span className="absolute left-0 right-0 -bottom-px h-0.5" style={{ backgroundColor: "#171A21" }} />}
              </button>
            ))}
          </div>

          {tab === "business" && (
            <div>
              <Field label="Business name"><input className={inputCls} value={state.name} onChange={(e) => setState({ ...state, name: e.target.value })} /></Field>
              <Field label="Industry">
                <select className={inputCls} value={state.industry} onChange={(e) => setState({ ...state, industry: e.target.value })}>
                  <option>Home services</option><option>Auto repair</option><option>Health & wellness</option><option>Professional services</option>
                </select>
              </Field>
              <Field label="How should it sound to customers?">
                <div className="grid sm:grid-cols-3 gap-2.5">
                  {TONE_OPTIONS.map(([label, desc]) => (
                    <ToneOption key={label} label={label} desc={desc} active={state.tone === label} onClick={() => setState({ ...state, tone: label })} />
                  ))}
                </div>
              </Field>
            </div>
          )}

          {tab === "services" && (
            <Field label="What you offer" hint="These are what it books, quotes, and answers questions about.">
              <div className="flex flex-wrap gap-2 mb-3">
                {state.services.map((s) => (
                  <span key={s} className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm bg-[#F1F1EF] border border-[#E7E5DE]">
                    {s} <X size={12} className="cursor-pointer text-[#9AA1AC]" onClick={() => removeService(s)} />
                  </span>
                ))}
              </div>
              <div className="flex gap-2">
                <input className={inputCls} placeholder="Add a service" value={newService} onChange={(e) => setNewService(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addService())} />
                <button onClick={addService} className="px-4 rounded-lg text-white text-sm font-medium flex items-center gap-1.5 shrink-0" style={{ backgroundColor: "#171A21" }}>
                  <Plus size={14} /> Add
                </button>
              </div>
            </Field>
          )}

          {tab === "area" && (
            <div>
              <Field label="Service radius" hint={`${state.radius} miles from your base zip code`}>
                <input type="range" min="5" max="60" value={state.radius} onChange={(e) => setState({ ...state, radius: Number(e.target.value) })} className="w-full accent-[#3A3EA6]" />
              </Field>
              <Field label="Known service zip codes" hint="Comma-separated — the engine matches against these first">
                <textarea className={inputCls} rows={3} value={state.zips} onChange={(e) => setState({ ...state, zips: e.target.value })} />
              </Field>
            </div>
          )}

          {tab === "questions" && (
            <div>
              <p className="text-sm text-[#6B7280] mb-6">Per service, the questions your engine confirms before booking.</p>
              {state.services.map((svc) => (
                <div key={svc} className="mb-5 pb-5 border-b border-[#F0EFE9] last:border-0">
                  <div className="text-sm font-semibold mb-2.5">{svc}</div>
                  <div className="flex flex-col gap-2">
                    {(state.questions[svc] || ["What's the issue you're experiencing?"]).map((q, i) => (
                      <div key={i} className="flex items-center gap-2">
                        <span className="text-xs text-[#9AA1AC] w-5 shrink-0" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>{i + 1}</span>
                        <input
                          className={inputCls}
                          value={q}
                          onChange={(e) => {
                            const qs = [...(state.questions[svc] || [])];
                            qs[i] = e.target.value;
                            setState({ ...state, questions: { ...state.questions, [svc]: qs } });
                          }}
                        />
                      </div>
                    ))}
                    <button
                      className="text-xs font-medium text-[#3A3EA6] flex items-center gap-1 mt-0.5 ml-7"
                      onClick={() => setState({ ...state, questions: { ...state.questions, [svc]: [...(state.questions[svc] || []), ""] } })}
                    >
                      <Plus size={12} /> Add question
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {tab === "escalation" && (
            <div className="flex flex-col gap-3">
              <p className="text-sm text-[#6B7280] mb-1">The engine never guesses past these lines — it stops and asks.</p>
              {ESCALATION_OPTIONS.map(([key, title, desc]) => (
                <label
                  key={key}
                  className="flex items-start gap-3 p-4 rounded-xl border cursor-pointer"
                  style={{ borderColor: state.escalation[key] ? "#3A3EA6" : "#E7E5DE", backgroundColor: state.escalation[key] ? "#EEEEF9" : "#fff" }}
                >
                  <input
                    type="checkbox"
                    checked={state.escalation[key]}
                    onChange={() => setState({ ...state, escalation: { ...state.escalation, [key]: !state.escalation[key] } })}
                    className="mt-0.5 accent-[#3A3EA6]"
                  />
                  <div>
                    <div className="text-sm font-medium">{title}</div>
                    <div className="text-xs text-[#6B7280] mt-0.5">{desc}</div>
                  </div>
                </label>
              ))}
            </div>
          )}
        </div>

        {dirty && (
          <div className="sticky bottom-0 border-t border-[#E7E5DE] bg-white px-6 md:px-8 py-4 flex items-center justify-between">
            <span className="text-xs text-[#6B7280]">This won't change how existing conversations behave — only new ones.</span>
            <div className="flex items-center gap-2">
              <button onClick={discard} className="text-sm font-medium px-4 py-2.5 rounded-lg border border-[#E7E5DE] flex items-center gap-1.5"><RotateCcw size={13} /> Discard</button>
              <button onClick={save} className="text-sm font-medium text-white px-5 py-2.5 rounded-lg" style={{ backgroundColor: "#171A21" }}>Save changes</button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
