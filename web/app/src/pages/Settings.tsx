import { useEffect, useMemo, useState } from "react";
import { Check, Loader2, Plus, RotateCcw, X } from "lucide-react";
import { Sidebar } from "../components/Sidebar";
import { Field, formatRelativeTime, inputCls, ToneOption } from "../components/Shared";
import { useAuth, describeError } from "../auth/AuthContext";
import { api, type BusinessDNASettings } from "../api/client";

const SETTINGS_TABS = [
  { key: "business", label: "Business" },
  { key: "services", label: "Services" },
  { key: "area", label: "Service area" },
  { key: "questions", label: "Questions" },
  { key: "escalation", label: "Escalation" },
] as const;

type TabKey = (typeof SETTINGS_TABS)[number]["key"];

interface DNAServiceState {
  /** Client-only identity so React keys and cross-tab references (Services <-> Questions)
   * stay stable for a brand-new service that has no real `id` yet (assigned on first save). */
  key: string;
  id: string | null;
  name: string;
  questions: string[];
}

interface SettingsState {
  name: string;
  industry: string;
  tone: string;
  services: DNAServiceState[];
  zips: string;
  escalation: { highUrgency: boolean; emergency: boolean };
}

/** Preset labels map to the exact copy `src/domain/business_dna_builder.py::_TONE_COPY`
 * stores in `communication.tone` — matching text is how the picker knows which preset
 * (if any) is currently active, since the field itself is just free text server-side. */
const TONE_PRESETS: { label: string; desc: string; copy: string }[] = [
  { label: "Friendly & direct", desc: "Warm, no filler", copy: "friendly, direct, and concise" },
  { label: "Formal & precise", desc: "Professional tone", copy: "formal, precise, and professional" },
  { label: "Casual & brief", desc: "Short, plain texts", copy: "casual, brief, and plainspoken" },
];

/** Both map to real `intent.urgency` values the engine extracts per message (see
 * `Urgency` in src/domain/qualification.py) — `QualificationService.evaluate()` checks
 * `intent.urgency.value in business_dna["human_escalation"]["triggers"]` directly, so
 * these two checkboxes are the actual, live escalation switches, not illustrative ones. */
const ESCALATION_OPTIONS: [keyof SettingsState["escalation"], string, string][] = [
  ["highUrgency", "Customer describes it as high urgency", "Hands off to you instead of letting the engine keep qualifying on its own."],
  ["emergency", "Customer describes it as an emergency", "Always hands off immediately — no automated next step at all."],
];

let clientKeySeq = 0;
function nextClientKey(): string {
  clientKeySeq += 1;
  return `svc-${clientKeySeq}-${Date.now()}`;
}

function fromServer(dna: BusinessDNASettings): SettingsState {
  return {
    name: dna.name,
    industry: dna.industry,
    tone: dna.tone,
    services: dna.services.map((s) => ({ key: nextClientKey(), id: s.id, name: s.name, questions: [...s.questions] })),
    zips: dna.service_zip_codes.join(", "),
    escalation: { highUrgency: dna.escalate_on_high_urgency, emergency: dna.escalate_on_emergency },
  };
}

export default function Settings() {
  const { token, user } = useAuth();
  const [tab, setTab] = useState<TabKey>("business");
  const [state, setState] = useState<SettingsState | null>(null);
  const [baseline, setBaseline] = useState<SettingsState | null>(null);
  const [version, setVersion] = useState<number | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [newService, setNewService] = useState("");

  useEffect(() => {
    let cancelled = false;
    if (!token || !user?.business_id) return;
    setLoading(true);
    setLoadError(null);
    api
      .getBusinessDNASettings(token, user.business_id)
      .then((dna) => {
        if (cancelled) return;
        const mapped = fromServer(dna);
        setState(mapped);
        setBaseline(mapped);
        setVersion(dna.version);
        setUpdatedAt(dna.updated_at);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(describeError(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, user?.business_id]);

  const dirty = useMemo(
    () => !!state && !!baseline && JSON.stringify(state) !== JSON.stringify(baseline),
    [state, baseline],
  );

  const zipList = useMemo(
    () => (state ? state.zips.split(",").map((z) => z.trim()).filter(Boolean) : []),
    [state],
  );
  const canSave =
    !!state &&
    state.name.trim().length > 0 &&
    state.industry.trim().length > 0 &&
    state.services.length > 0 &&
    state.services.every((s) => s.name.trim().length > 0) &&
    zipList.length > 0;

  const addService = () => {
    const v = newService.trim();
    if (!state || !v) return;
    if (state.services.some((s) => s.name.toLowerCase() === v.toLowerCase())) return;
    setState({ ...state, services: [...state.services, { key: nextClientKey(), id: null, name: v, questions: [] }] });
    setNewService("");
  };
  const removeService = (key: string) => {
    if (!state) return;
    setState({ ...state, services: state.services.filter((s) => s.key !== key) });
  };

  const save = async () => {
    if (!token || !user?.business_id || !state || !canSave) return;
    setSaving(true);
    setSaveError(null);
    try {
      const dna = await api.updateBusinessDNASettings(token, user.business_id, {
        name: state.name.trim(),
        industry: state.industry.trim(),
        tone: state.tone,
        services: state.services.map((s) => ({
          id: s.id ?? undefined,
          name: s.name.trim(),
          questions: s.questions.map((q) => q.trim()).filter(Boolean),
        })),
        service_zip_codes: zipList,
        escalate_on_high_urgency: state.escalation.highUrgency,
        escalate_on_emergency: state.escalation.emergency,
      });
      const mapped = fromServer(dna);
      // Keep the client-only keys we already had (by position — the server returns
      // services in the same order we submitted them) so inputs don't remount and
      // lose focus/selection right after a save.
      const services = mapped.services.map((s, i) => ({ ...s, key: state.services[i]?.key ?? s.key }));
      const next = { ...mapped, services };
      setState(next);
      setBaseline(next);
      setVersion(dna.version);
      setUpdatedAt(dna.updated_at);
    } catch (err) {
      setSaveError(describeError(err));
    } finally {
      setSaving(false);
    }
  };
  const discard = () => {
    setState(baseline);
    setSaveError(null);
  };

  return (
    <div className="min-h-screen w-full flex" style={{ backgroundColor: "#F7F6F2", fontFamily: "'Inter', sans-serif", color: "#171A21" }}>
      <Sidebar />
      <main className="flex-1 min-w-0 flex flex-col">
        <header className="flex items-center justify-between px-6 md:px-8 py-4 border-b border-[#E7E5DE]">
          <div>
            <h1 className="text-xl" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>Business DNA</h1>
            <p className="text-sm text-[#6B7280] mt-0.5" style={{ fontFamily: dirty ? "'Inter', sans-serif" : "'IBM Plex Mono', monospace" }}>
              {dirty
                ? "Unsaved changes"
                : updatedAt
                  ? `Last updated ${formatRelativeTime(updatedAt)}${version ? ` · v${version}` : ""}`
                  : "Loading…"}
            </p>
          </div>
          {!dirty && state && (
            <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full" style={{ color: "#1E7B52", backgroundColor: "#E9F5EF" }}>
              <Check size={12} /> Live
            </span>
          )}
        </header>

        {loading && (
          <div className="flex items-center gap-2 text-sm text-[#6B7280] py-16 justify-center">
            <Loader2 size={16} className="animate-spin" /> Loading…
          </div>
        )}

        {!loading && loadError && (
          <div className="max-w-3xl px-6 md:px-8 py-8 w-full">
            <div className="px-4 py-3 rounded-lg text-sm" style={{ backgroundColor: "#FBEBE9", color: "#8A3225" }}>
              {loadError}
            </div>
          </div>
        )}

        {!loading && !loadError && state && (
          <>
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
                  <Field label="Industry"><input className={inputCls} value={state.industry} onChange={(e) => setState({ ...state, industry: e.target.value })} /></Field>
                  <Field label="How should it sound to customers?">
                    <div className="grid sm:grid-cols-3 gap-2.5">
                      {TONE_PRESETS.map((preset) => (
                        <ToneOption
                          key={preset.label}
                          label={preset.label}
                          desc={preset.desc}
                          active={state.tone === preset.copy}
                          onClick={() => setState({ ...state, tone: preset.copy })}
                        />
                      ))}
                    </div>
                  </Field>
                </div>
              )}

              {tab === "services" && (
                <Field label="What you offer" hint="These are what it books, quotes, and answers questions about.">
                  <div className="flex flex-wrap gap-2 mb-3">
                    {state.services.map((s) => (
                      <span key={s.key} className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm bg-[#F1F1EF] border border-[#E7E5DE]">
                        {s.name} <X size={12} className="cursor-pointer text-[#9AA1AC]" onClick={() => removeService(s.key)} />
                      </span>
                    ))}
                    {state.services.length === 0 && <span className="text-xs text-[#9AA1AC]">No services yet — add at least one.</span>}
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
                <Field label="Known service zip codes" hint="Comma-separated — the engine matches a customer's stated zip against these first, and treats anything else as outside your area.">
                  <textarea className={inputCls} rows={3} value={state.zips} onChange={(e) => setState({ ...state, zips: e.target.value })} />
                  {zipList.length === 0 && <p className="text-xs mt-2" style={{ color: "#B4483A" }}>At least one zip code is required.</p>}
                </Field>
              )}

              {tab === "questions" && (
                <div>
                  <p className="text-sm text-[#6B7280] mb-6">Per service, the questions your engine confirms before booking.</p>
                  {state.services.length === 0 && <p className="text-sm text-[#9AA1AC]">Add a service on the Services tab first.</p>}
                  {state.services.map((svc) => (
                    <div key={svc.key} className="mb-5 pb-5 border-b border-[#F0EFE9] last:border-0">
                      <div className="text-sm font-semibold mb-2.5">{svc.name}</div>
                      <div className="flex flex-col gap-2">
                        {svc.questions.map((q, i) => (
                          <div key={i} className="flex items-center gap-2">
                            <span className="text-xs text-[#9AA1AC] w-5 shrink-0" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>{i + 1}</span>
                            <input
                              className={inputCls}
                              value={q}
                              onChange={(e) => {
                                const services = state.services.map((s) =>
                                  s.key === svc.key ? { ...s, questions: s.questions.map((qq, qi) => (qi === i ? e.target.value : qq)) } : s,
                                );
                                setState({ ...state, services });
                              }}
                            />
                            <X
                              size={14}
                              className="cursor-pointer text-[#9AA1AC] shrink-0"
                              onClick={() => {
                                const services = state.services.map((s) =>
                                  s.key === svc.key ? { ...s, questions: s.questions.filter((_, qi) => qi !== i) } : s,
                                );
                                setState({ ...state, services });
                              }}
                            />
                          </div>
                        ))}
                        <button
                          className="text-xs font-medium text-[#3A3EA6] flex items-center gap-1 mt-0.5 ml-7"
                          onClick={() => {
                            const services = state.services.map((s) => (s.key === svc.key ? { ...s, questions: [...s.questions, ""] } : s));
                            setState({ ...state, services });
                          }}
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
              <div className="sticky bottom-0 border-t border-[#E7E5DE] bg-white px-6 md:px-8 py-4 flex items-center justify-between gap-4">
                <span className="text-xs text-[#6B7280]">
                  {saveError ?? "This won't change how existing conversations behave — only new ones."}
                </span>
                <div className="flex items-center gap-2 shrink-0">
                  <button onClick={discard} disabled={saving} className="text-sm font-medium px-4 py-2.5 rounded-lg border border-[#E7E5DE] flex items-center gap-1.5 disabled:opacity-50">
                    <RotateCcw size={13} /> Discard
                  </button>
                  <button onClick={save} disabled={!canSave || saving} className="text-sm font-medium text-white px-5 py-2.5 rounded-lg flex items-center gap-1.5 disabled:opacity-50" style={{ backgroundColor: "#171A21" }}>
                    {saving && <Loader2 size={13} className="animate-spin" />}
                    Save changes
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
