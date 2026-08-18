import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, Check, ChevronLeft, ChevronRight, Globe, Loader2, MapPin, MessageSquare, Plus, RotateCcw, X } from "lucide-react";
import { Sidebar } from "../components/Sidebar";
import { AreaOption, Field, formatRelativeTime, inputCls, ToneOption } from "../components/Shared";
import { useAuth, describeError } from "../auth/AuthContext";
import { api, type BusinessDNASettings, type CommercialPath, type SmsStatus } from "../api/client";

// Grouped by the task a business owner actually has, not by which Business
// DNA schema section a field happens to live in -- "Services" and "Booking"
// used to be separate tabs even though a service only takes bookings once
// both its own "Book online" commercial path AND this section's timezone/hours
// are set; "Questions" and "Escalation" were split even though both are really
// "how the engine should handle the conversation." Four stops instead of
// seven the owner has to click through to find anything.
const SETTINGS_TABS = [
  { key: "basics", label: "Basics" },
  { key: "services", label: "Services & booking" },
  { key: "conversation", label: "Conversation" },
  { key: "sms", label: "SMS" },
] as const;

const WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"] as const;
type Weekday = (typeof WEEKDAYS)[number];
const WEEKDAY_LABELS: Record<Weekday, string> = {
  monday: "Mon", tuesday: "Tue", wednesday: "Wed", thursday: "Thu", friday: "Fri", saturday: "Sat", sunday: "Sun",
};
// Every value here is a real IANA zone the deterministic availability engine
// (src/engine/commercial.py) resolves via zoneinfo — this list is deliberately
// US-only since the product's market is US-only today.
const US_TIMEZONES: { value: string; label: string }[] = [
  { value: "America/New_York", label: "Eastern (New York)" },
  { value: "America/Chicago", label: "Central (Chicago)" },
  { value: "America/Denver", label: "Mountain (Denver)" },
  { value: "America/Phoenix", label: "Mountain, no DST (Phoenix)" },
  { value: "America/Los_Angeles", label: "Pacific (Los Angeles)" },
  { value: "America/Anchorage", label: "Alaska (Anchorage)" },
  { value: "Pacific/Honolulu", label: "Hawaii (Honolulu)" },
];

interface DayHoursState {
  open: boolean;
  opens: string;
  closes: string;
}
type WeekHoursState = Record<Weekday, DayHoursState>;

const DEFAULT_DAY_CLOSED: DayHoursState = { open: false, opens: "09:00", closes: "17:00" };

type TabKey = (typeof SETTINGS_TABS)[number]["key"];
const TAB_KEYS = new Set<string>(SETTINGS_TABS.map((t) => t.key));
function isTabKey(value: string | null): value is TabKey {
  return !!value && TAB_KEYS.has(value);
}

interface DNAServiceState {
  /** Client-only identity so React keys and cross-tab references (Services <-> Questions)
   * stay stable for a brand-new service that has no real `id` yet (assigned on first save). */
  key: string;
  id: string | null;
  name: string;
  questions: string[];
  /** What happens once a lead qualifies for this service — see
   * BusinessDNASettingsService._apply. "booking" only actually offers a slot
   * once the Booking tab's bookingEnabled is also on. */
  commercialPath: CommercialPath;
  /** Only used (and required) when commercialPath === "quote". Plain decimal
   * string, e.g. "150" or "89.50" — validated against the same pattern the
   * backend enforces (see _MONEY_PATTERN in business_dna_settings_service.py). */
  quotePrice: string;
  /** Only used (and required) when commercialPath === "direct_step". */
  nextStepMessage: string;
}

const QUOTE_PRICE_PATTERN = /^(0|[1-9][0-9]*)(\.[0-9]{1,2})?$/;

const COMMERCIAL_PATH_OPTIONS: { value: CommercialPath; label: string }[] = [
  { value: "booking", label: "Book online" },
  { value: "quote", label: "Send a price quote" },
  { value: "direct_step", label: "Send next steps" },
  { value: "human_review", label: "Always hand off to you" },
];

interface SettingsState {
  name: string;
  industry: string;
  tone: string;
  services: DNAServiceState[];
  /** "remote" = no fixed service area (business.service_zip_codes comes back
   * empty from the server whenever the active area is `remote` rather than
   * `postal_codes` — see BusinessDNASettingsResponse.from_domain). */
  areaMode: "remote" | "local";
  zips: string;
  escalation: { highUrgency: boolean; emergency: boolean };
  bookingEnabled: boolean;
  bookingTimezone: string;
  hours: WeekHoursState;
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
  const hours = WEEKDAYS.reduce((acc, day) => {
    const windows = dna.business_hours[day];
    acc[day] = windows && windows.length > 0
      ? { open: true, opens: windows[0].opens, closes: windows[0].closes }
      : { ...DEFAULT_DAY_CLOSED };
    return acc;
  }, {} as WeekHoursState);
  return {
    name: dna.name,
    industry: dna.industry,
    tone: dna.tone,
    services: dna.services.map((s) => ({
      key: nextClientKey(),
      id: s.id,
      name: s.name,
      questions: [...s.questions],
      commercialPath: s.commercial_path,
      quotePrice: s.quote_price ?? "",
      nextStepMessage: s.next_step_message ?? "",
    })),
    areaMode: dna.service_zip_codes.length === 0 ? "remote" : "local",
    zips: dna.service_zip_codes.join(", "),
    escalation: { highUrgency: dna.escalate_on_high_urgency, emergency: dna.escalate_on_emergency },
    bookingEnabled: dna.booking_enabled,
    bookingTimezone: dna.booking_timezone,
    hours,
  };
}

export default function Settings() {
  const navigate = useNavigate();
  const { token, businessId } = useAuth();
  // Kept in the URL (?tab=) rather than plain component state so a reload
  // -- or sharing/bookmarking the link -- lands back on the same tab
  // instead of always resetting to "business".
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const tab: TabKey = isTabKey(tabParam) ? tabParam : "basics";
  const setTab = (next: TabKey) => {
    setSearchParams((prev) => {
      const params = new URLSearchParams(prev);
      params.set("tab", next);
      return params;
    }, { replace: true });
  };
  const tabRailRef = useRef<HTMLDivElement>(null);
  const scrollTabRail = (direction: -1 | 1) => {
    tabRailRef.current?.scrollBy({ left: direction * 160, behavior: "smooth" });
  };
  const [state, setState] = useState<SettingsState | null>(null);
  const [baseline, setBaseline] = useState<SettingsState | null>(null);
  const [version, setVersion] = useState<number | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [newService, setNewService] = useState("");

  const [smsStatus, setSmsStatus] = useState<SmsStatus | null>(null);
  const [smsLoading, setSmsLoading] = useState(true);
  const [smsError, setSmsError] = useState<string | null>(null);
  const [smsProvisioning, setSmsProvisioning] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!token || !businessId) return;
    setLoading(true);
    setLoadError(null);
    api
      .getBusinessDNASettings(token, businessId)
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
  }, [token, businessId]);

  useEffect(() => {
    let cancelled = false;
    if (!token || !businessId) return;
    setSmsLoading(true);
    setSmsError(null);
    api
      .getSmsStatus(token, businessId)
      .then((status) => {
        if (!cancelled) setSmsStatus(status);
      })
      .catch((err) => {
        if (!cancelled) setSmsError(describeError(err));
      })
      .finally(() => {
        if (!cancelled) setSmsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, businessId]);

  const provisionSms = async () => {
    if (!token || !businessId) return;
    setSmsProvisioning(true);
    setSmsError(null);
    try {
      const status = await api.provisionSms(token, businessId);
      setSmsStatus(status);
    } catch (err) {
      setSmsError(describeError(err));
    } finally {
      setSmsProvisioning(false);
    }
  };

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
    state.services.every((s) => {
      if (s.commercialPath === "quote") return QUOTE_PRICE_PATTERN.test(s.quotePrice.trim());
      if (s.commercialPath === "direct_step") {
        const msg = s.nextStepMessage.trim();
        return msg.length > 0 && msg.length <= 1000;
      }
      return true;
    }) &&
    (state.areaMode === "remote" || zipList.length > 0);

  const addService = () => {
    const v = newService.trim();
    if (!state || !v) return;
    if (state.services.some((s) => s.name.toLowerCase() === v.toLowerCase())) return;
    setState({
      ...state,
      services: [
        ...state.services,
        { key: nextClientKey(), id: null, name: v, questions: [], commercialPath: "human_review", quotePrice: "", nextStepMessage: "" },
      ],
    });
    setNewService("");
  };
  const removeService = (key: string) => {
    if (!state) return;
    setState({ ...state, services: state.services.filter((s) => s.key !== key) });
  };

  const save = async () => {
    if (!token || !businessId || !state || !canSave) return;
    setSaving(true);
    setSaveError(null);
    try {
      const dna = await api.updateBusinessDNASettings(token, businessId, {
        name: state.name.trim(),
        industry: state.industry.trim(),
        tone: state.tone,
        services: state.services.map((s) => ({
          id: s.id ?? undefined,
          name: s.name.trim(),
          questions: s.questions.map((q) => q.trim()).filter(Boolean),
          commercial_path: s.commercialPath,
          quote_price: s.commercialPath === "quote" ? s.quotePrice.trim() : null,
          next_step_message: s.commercialPath === "direct_step" ? s.nextStepMessage.trim() : null,
        })),
        service_zip_codes: state.areaMode === "local" ? zipList : [],
        escalate_on_high_urgency: state.escalation.highUrgency,
        escalate_on_emergency: state.escalation.emergency,
        booking_enabled: state.bookingEnabled,
        booking_timezone: state.bookingTimezone,
        business_hours: WEEKDAYS.reduce((acc, day) => {
          const d = state.hours[day];
          if (d.open) acc[day] = [{ opens: d.opens, closes: d.closes }];
          return acc;
        }, {} as Record<string, { opens: string; closes: string }[]>),
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
    <div className="min-h-screen w-full flex" style={{ backgroundColor: "#F5F1EA", fontFamily: "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif", color: "#151515" }}>
      <Sidebar />
      <main className="flex-1 min-w-0 flex flex-col pt-14 md:pt-0">
        <header className="flex items-center justify-between px-6 md:px-8 py-4 border-b border-[#E7E5DE]">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate("/app")}
              aria-label="Back to Overview"
              className="md:hidden -ml-1.5 p-1.5 rounded-lg shrink-0"
              style={{ color: "#6B6459" }}
            >
              <ArrowLeft size={18} />
            </button>
            <div>
              <h1 className="text-xl" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}>Settings</h1>
              <p className="text-sm text-[#6B6459] mt-0.5" style={{ fontFamily: dirty ? "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif" : "'IBM Plex Mono', monospace" }}>
                {dirty
                  ? "Unsaved changes"
                  : updatedAt
                    ? `Last updated ${formatRelativeTime(updatedAt)}${version ? ` · v${version}` : ""}`
                    : "Loading…"}
              </p>
            </div>
          </div>
          {!dirty && state && (
            <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full" style={{ color: "#1E7B52", backgroundColor: "#E9F5EF" }}>
              <Check size={12} /> Live
            </span>
          )}
        </header>

        {loading && (
          <div className="flex items-center gap-2 text-sm text-[#6B6459] py-16 justify-center">
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
              <div className="flex items-center gap-1 mb-8 border-b border-[#E7E5DE]">
                <button
                  onClick={() => scrollTabRail(-1)}
                  aria-label="Scroll tabs left"
                  className="md:hidden shrink-0 p-1 -mb-px"
                  style={{ color: "#9C9488" }}
                >
                  <ChevronLeft size={16} />
                </button>
                <div ref={tabRailRef} className="flex items-center gap-1 overflow-x-auto scroll-smooth">
                  {SETTINGS_TABS.map((t) => (
                    <button
                      key={t.key}
                      onClick={() => setTab(t.key)}
                      className="px-3.5 py-2.5 text-sm whitespace-nowrap relative -mb-px shrink-0"
                      style={{ color: tab === t.key ? "#151515" : "#9C9488", fontWeight: tab === t.key ? 600 : 500 }}
                    >
                      {t.label}
                      {tab === t.key && <span className="absolute left-0 right-0 -bottom-px h-0.5" style={{ backgroundColor: "#151515" }} />}
                    </button>
                  ))}
                </div>
                <button
                  onClick={() => scrollTabRail(1)}
                  aria-label="Scroll tabs right"
                  className="md:hidden shrink-0 p-1 -mb-px"
                  style={{ color: "#9C9488" }}
                >
                  <ChevronRight size={16} />
                </button>
              </div>

              {tab === "basics" && (
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

                  <div className="text-sm font-semibold mt-8 mb-4 pt-6 border-t border-[#F0EFE9]">Who you serve</div>
                  <div className="grid sm:grid-cols-2 gap-3 mb-5">
                    <AreaOption
                      icon={Globe}
                      label="Anywhere"
                      desc="Fully remote or online — no fixed location. Every lead qualifies regardless of where they're based."
                      active={state.areaMode === "remote"}
                      onClick={() => setState({ ...state, areaMode: "remote" })}
                    />
                    <AreaOption
                      icon={MapPin}
                      label="A specific area"
                      desc="Only leads inside the zip codes you list book automatically — others go to you instead."
                      active={state.areaMode === "local"}
                      onClick={() => setState({ ...state, areaMode: "local" })}
                    />
                  </div>
                  {state.areaMode === "local" && (
                    <Field label="Known service zip codes" hint="Comma-separated — the engine matches a customer's stated zip against these first, and treats anything else as outside your area.">
                      <textarea className={inputCls} rows={3} value={state.zips} onChange={(e) => setState({ ...state, zips: e.target.value })} />
                      {zipList.length === 0 && <p className="text-xs mt-2" style={{ color: "#B4483A" }}>At least one zip code is required.</p>}
                    </Field>
                  )}
                </div>
              )}

              {tab === "services" && (
                <div>
                  <Field label="What you offer" hint="These are what it books, quotes, and answers questions about.">
                    <div className="flex flex-wrap gap-2 mb-3">
                      {state.services.map((s) => (
                        <span key={s.key} className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm bg-[#F1F1EF] border border-[#E7E5DE]">
                          {s.name} <X size={12} className="cursor-pointer text-[#9C9488]" onClick={() => removeService(s.key)} />
                        </span>
                      ))}
                      {state.services.length === 0 && <span className="text-xs text-[#9C9488]">No services yet — add at least one.</span>}
                    </div>
                    <div className="flex gap-2">
                      <input className={inputCls} placeholder="Add a service" value={newService} onChange={(e) => setNewService(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addService())} />
                      <button onClick={addService} className="px-4 rounded-lg text-white text-sm font-medium flex items-center gap-1.5 shrink-0" style={{ backgroundColor: "#151515" }}>
                        <Plus size={14} /> Add
                      </button>
                    </div>
                  </Field>

                  <div className="text-sm font-semibold mt-8 mb-2 pt-6 border-t border-[#F0EFE9]">Online booking</div>
                  <p className="text-sm text-[#6B6459] mb-6">
                    Let clients pick a real open slot and get booked automatically — no back-and-forth.
                    Only services set to "Book online" below are offered a slot; this needs to be on
                    for that to actually happen.
                  </p>
                  <label className="flex items-start gap-3 p-4 rounded-xl border cursor-pointer mb-6" style={{ borderColor: state.bookingEnabled ? "#B87333" : "#E7E5DE", backgroundColor: state.bookingEnabled ? "#F5E7D6" : "#fff" }}>
                    <input
                      type="checkbox"
                      checked={state.bookingEnabled}
                      onChange={() => setState({ ...state, bookingEnabled: !state.bookingEnabled })}
                      className="mt-0.5 accent-[#B87333]"
                    />
                    <div>
                      <div className="text-sm font-medium">Turn on online booking</div>
                      <div className="text-xs text-[#6B6459] mt-0.5">Off by default — until this is on, every qualified lead still goes to you instead of getting a slot.</div>
                    </div>
                  </label>

                  <Field label="What happens once a lead qualifies for each service?" hint="Book online offers a real slot. Send a price quote gives an automatic fixed price. Send next steps replies with instructions instead of a price or a slot. Always hand off to you sends every qualified lead your way.">
                    <div className="flex flex-col gap-4">
                      {state.services.length === 0 && <span className="text-xs text-[#9C9488]">Add a service above first.</span>}
                      {state.services.map((s) => (
                        <div key={s.key} className="p-3 rounded-xl border border-[#E7E5DE]">
                          <div className="flex items-center gap-3 flex-wrap">
                            <span className="text-sm font-medium min-w-0 flex-1">{s.name}</span>
                            <select
                              className={inputCls}
                              style={{ width: "auto", minWidth: 200 }}
                              value={s.commercialPath}
                              onChange={(e) => {
                                const commercialPath = e.target.value as CommercialPath;
                                const services = state.services.map((svc) =>
                                  svc.key === s.key ? { ...svc, commercialPath } : svc,
                                );
                                setState({ ...state, services });
                              }}
                            >
                              {COMMERCIAL_PATH_OPTIONS.map((opt) => (
                                <option key={opt.value} value={opt.value}>{opt.label}</option>
                              ))}
                            </select>
                          </div>
                          {s.commercialPath === "quote" && (
                            <div className="mt-3">
                              <label className="text-xs text-[#6B6459] block mb-1">Fixed price ($)</label>
                              <input
                                className={inputCls}
                                style={{ width: 160 }}
                                placeholder="e.g. 150"
                                inputMode="decimal"
                                value={s.quotePrice}
                                onChange={(e) => {
                                  const services = state.services.map((svc) =>
                                    svc.key === s.key ? { ...svc, quotePrice: e.target.value } : svc,
                                  );
                                  setState({ ...state, services });
                                }}
                              />
                              {!QUOTE_PRICE_PATTERN.test(s.quotePrice.trim()) && (
                                <p className="text-xs mt-1.5" style={{ color: "#B4483A" }}>Enter a price like 150 or 89.50.</p>
                              )}
                            </div>
                          )}
                          {s.commercialPath === "direct_step" && (
                            <div className="mt-3">
                              <label className="text-xs text-[#6B6459] block mb-1">Message to send</label>
                              <textarea
                                className={inputCls}
                                rows={2}
                                placeholder="e.g. Head to our online store to place your order: ..."
                                value={s.nextStepMessage}
                                onChange={(e) => {
                                  const services = state.services.map((svc) =>
                                    svc.key === s.key ? { ...svc, nextStepMessage: e.target.value } : svc,
                                  );
                                  setState({ ...state, services });
                                }}
                              />
                              {s.nextStepMessage.trim().length === 0 && (
                                <p className="text-xs mt-1.5" style={{ color: "#B4483A" }}>A message is required.</p>
                              )}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </Field>

                  <Field label="Time zone" hint="Slot times are calculated in this zone.">
                    <select
                      className={inputCls}
                      value={state.bookingTimezone}
                      onChange={(e) => setState({ ...state, bookingTimezone: e.target.value })}
                    >
                      {US_TIMEZONES.map((tz) => (
                        <option key={tz.value} value={tz.value}>{tz.label}</option>
                      ))}
                    </select>
                  </Field>

                  <Field label="Open hours" hint="Uncheck a day to keep it closed. Slots are only offered inside these windows.">
                    <div className="flex flex-col gap-2">
                      {WEEKDAYS.map((day) => {
                        const d = state.hours[day];
                        return (
                          <div key={day} className="flex items-center gap-3">
                            <label className="flex items-center gap-2 w-24 shrink-0 text-sm cursor-pointer">
                              <input
                                type="checkbox"
                                checked={d.open}
                                onChange={() => setState({ ...state, hours: { ...state.hours, [day]: { ...d, open: !d.open } } })}
                                className="accent-[#B87333]"
                              />
                              {WEEKDAY_LABELS[day]}
                            </label>
                            <input
                              type="time"
                              className={inputCls}
                              disabled={!d.open}
                              value={d.opens}
                              onChange={(e) => setState({ ...state, hours: { ...state.hours, [day]: { ...d, opens: e.target.value } } })}
                            />
                            <span className="text-xs text-[#9C9488]">to</span>
                            <input
                              type="time"
                              className={inputCls}
                              disabled={!d.open}
                              value={d.closes}
                              onChange={(e) => setState({ ...state, hours: { ...state.hours, [day]: { ...d, closes: e.target.value } } })}
                            />
                          </div>
                        );
                      })}
                    </div>
                  </Field>
                </div>
              )}

              {tab === "conversation" && (
                <div>
                  <p className="text-sm text-[#6B6459] mb-6">Per service, the questions your engine confirms before booking.</p>
                  {state.services.length === 0 && <p className="text-sm text-[#9C9488]">Add a service on the Services & booking tab first.</p>}
                  {state.services.map((svc) => (
                    <div key={svc.key} className="mb-5 pb-5 border-b border-[#F0EFE9] last:border-0">
                      <div className="text-sm font-semibold mb-2.5">{svc.name}</div>
                      <div className="flex flex-col gap-2">
                        {svc.questions.map((q, i) => (
                          <div key={i} className="flex items-center gap-2">
                            <span className="text-xs text-[#9C9488] w-5 shrink-0" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>{i + 1}</span>
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
                              className="cursor-pointer text-[#9C9488] shrink-0"
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
                          className="text-xs font-medium text-[#B87333] flex items-center gap-1 mt-0.5 ml-7"
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

                  <div className="text-sm font-semibold mt-8 mb-2 pt-6 border-t border-[#F0EFE9]">Escalation</div>
                  <p className="text-sm text-[#6B6459] mb-4">The engine never guesses past these lines — it stops and asks.</p>
                  <div className="flex flex-col gap-3">
                    {ESCALATION_OPTIONS.map(([key, title, desc]) => (
                      <label
                        key={key}
                        className="flex items-start gap-3 p-4 rounded-xl border cursor-pointer"
                        style={{ borderColor: state.escalation[key] ? "#B87333" : "#E7E5DE", backgroundColor: state.escalation[key] ? "#F5E7D6" : "#fff" }}
                      >
                        <input
                          type="checkbox"
                          checked={state.escalation[key]}
                          onChange={() => setState({ ...state, escalation: { ...state.escalation, [key]: !state.escalation[key] } })}
                          className="mt-0.5 accent-[#B87333]"
                        />
                        <div>
                          <div className="text-sm font-medium">{title}</div>
                          <div className="text-xs text-[#6B6459] mt-0.5">{desc}</div>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              {tab === "sms" && (
                <div>
                  <p className="text-sm text-[#6B6459] mb-6">
                    Give leads a phone number that texts straight into your engine — the same qualification and
                    booking logic that runs on your website runs here too.
                  </p>
                  {smsLoading && (
                    <div className="flex items-center gap-2 text-sm text-[#6B6459] py-6">
                      <Loader2 size={16} className="animate-spin" /> Checking status…
                    </div>
                  )}
                  {!smsLoading && smsStatus && !smsStatus.configured && (
                    <div className="px-4 py-3 rounded-lg text-sm" style={{ backgroundColor: "#F1F1EF", color: "#6B6459" }}>
                      SMS delivery isn't set up on this deployment yet.
                    </div>
                  )}
                  {!smsLoading && smsStatus?.configured && smsStatus.phone_number && (
                    <div className="flex items-center gap-3 p-4 rounded-xl border" style={{ borderColor: "#E7E5DE" }}>
                      <span className="flex items-center justify-center rounded-full shrink-0" style={{ width: 36, height: 36, backgroundColor: "#E9F5EF", color: "#1E7B52" }}>
                        <MessageSquare size={16} />
                      </span>
                      <div>
                        <div className="text-sm font-medium" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>{smsStatus.phone_number}</div>
                        <div className="text-xs text-[#6B6459] mt-0.5">Texts to this number reach your engine automatically.</div>
                      </div>
                    </div>
                  )}
                  {!smsLoading && smsStatus?.configured && !smsStatus.phone_number && (
                    <div className="p-4 rounded-xl border border-[#E7E5DE]">
                      <div className="text-sm font-medium mb-1">No number yet</div>
                      <div className="text-xs text-[#6B6459] mb-3">Set up a dedicated SMS number for your business — this takes a few seconds.</div>
                      <button
                        onClick={provisionSms}
                        disabled={smsProvisioning}
                        className="text-sm font-medium text-white px-4 py-2.5 rounded-lg flex items-center gap-1.5 disabled:opacity-50"
                        style={{ backgroundColor: "#151515" }}
                      >
                        {smsProvisioning && <Loader2 size={13} className="animate-spin" />}
                        Set up SMS
                      </button>
                    </div>
                  )}
                  {smsError && (
                    <div className="mt-3 px-4 py-3 rounded-lg text-sm flex items-center justify-between gap-3" style={{ backgroundColor: "#FBEBE9", color: "#8A3225" }}>
                      <span>{smsError}</span>
                      {smsStatus?.configured && (
                        <button onClick={provisionSms} disabled={smsProvisioning} className="text-xs font-medium underline shrink-0 disabled:opacity-50">
                          Retry
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            {dirty && (
              <div className="sticky bottom-0 border-t border-[#E7E5DE] bg-white px-6 md:px-8 py-4 flex items-center justify-between gap-4">
                <span className="text-xs text-[#6B6459]">
                  {saveError ?? "This won't change how existing conversations behave — only new ones."}
                </span>
                <div className="flex items-center gap-2 shrink-0">
                  <button onClick={discard} disabled={saving} className="text-sm font-medium px-4 py-2.5 rounded-lg border border-[#E7E5DE] flex items-center gap-1.5 disabled:opacity-50">
                    <RotateCcw size={13} /> Discard
                  </button>
                  <button onClick={save} disabled={!canSave || saving} className="text-sm font-medium text-white px-5 py-2.5 rounded-lg flex items-center gap-1.5 disabled:opacity-50" style={{ backgroundColor: "#151515" }}>
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
