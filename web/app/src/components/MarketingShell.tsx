import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Menu, X } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { FlywheelMark } from "./Shared";
import { setPageMeta } from "../lib/pageMeta";

export const MARKETING_BODY =
  "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif";
export const MARKETING_DISPLAY =
  "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif";

const CYCLE = [
  "New",
  "Contacted",
  "Qualifying",
  "Quoted / booked",
  "Follow-up",
  "Won",
];

export function DealCycle({ compact }: { compact?: boolean }) {
  return (
    <div
      className={`flex flex-wrap items-center gap-1 ${compact ? "" : "py-1"}`}
      aria-label="Lead-to-deal cycle"
    >
      {CYCLE.map((label, i) => (
        <div key={label} className="flex items-center gap-1 shrink-0">
          <span
            className="text-[11px] font-medium uppercase tracking-wide px-2.5 py-1 rounded-full whitespace-nowrap"
            style={{
              backgroundColor: i === CYCLE.length - 1 ? "#151515" : "#F5E7D6",
              color: i === CYCLE.length - 1 ? "#F5F1EA" : "#B87333",
            }}
          >
            {label}
          </span>
          {i < CYCLE.length - 1 && (
            <span className="text-[#D9D4C8] text-xs px-0.5" aria-hidden>
              →
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

export function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-[#E7E5DE] last:border-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-start justify-between gap-4 py-5 text-left"
        aria-expanded={open}
      >
        <span className="text-sm font-semibold">{q}</span>
        <span className="text-[#9C9488] text-lg leading-none shrink-0 mt-0.5">{open ? "–" : "+"}</span>
      </button>
      {open && <p className="text-sm text-[#6B6459] leading-relaxed pb-5 pr-8">{a}</p>}
    </div>
  );
}

/**
 * Shared chrome for public marketing pages. Logo always goes home (/) —
 * Wave 1 attorney outreach lives at /lawyers as a campaign page, never as
 * the product's identity. See docs/marketing/06-speed-to-revenue-playbook.md.
 */
export function MarketingShell({
  variant,
  title,
  description,
  children,
}: {
  variant: "product" | "attorneys";
  title: string;
  description: string;
  children: ReactNode;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const navigate = useNavigate();
  const { user } = useAuth();
  const primaryCtaTarget = user ? (user.business_ids.length > 0 ? "/app" : "/onboarding") : "/signup";
  const ctaLabel = user ? "Go to dashboard" : "Start free trial";

  useEffect(() => {
    setPageMeta(title, description);
  }, [title, description]);

  const nav =
    variant === "attorneys"
      ? [
          { href: "#different", label: "How it's different", type: "hash" as const },
          { href: "#pricing", label: "Pricing", type: "hash" as const },
          { href: "#faq", label: "FAQ", type: "hash" as const },
          { href: "/", label: "All businesses", type: "route" as const },
        ]
      : [
          { href: "#how", label: "How it works", type: "hash" as const },
          { href: "#pricing", label: "Pricing", type: "hash" as const },
          { href: "/lawyers", label: "For attorneys", type: "route" as const },
        ];

  function go(item: (typeof nav)[number]) {
    setMenuOpen(false);
    if (item.type === "route") navigate(item.href);
  }

  return (
    <div
      style={{ backgroundColor: "#F5F1EA", fontFamily: MARKETING_BODY, color: "#151515" }}
      className="min-h-screen w-full pb-24 md:pb-0"
    >
      <header
        className="sticky top-0 z-20 backdrop-blur-sm"
        style={{ backgroundColor: "#F5F1EAEE", borderBottom: "1px solid #E7E5DE" }}
      >
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <button onClick={() => navigate("/")} className="flex items-center gap-2" aria-label="Flywheel home">
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center text-white"
              style={{ backgroundColor: "#B87333" }}
            >
              <FlywheelMark size={16} />
            </div>
            <span className="font-semibold text-sm" style={{ fontFamily: MARKETING_DISPLAY }}>
              Flywheel
            </span>
          </button>
          <nav className="hidden md:flex items-center gap-8 text-xs font-medium uppercase tracking-wider text-[#6B6459]">
            {nav.map((item) =>
              item.type === "hash" ? (
                <a key={item.href} href={item.href} className="hover:text-[#151515] transition-colors">
                  {item.label}
                </a>
              ) : (
                <button key={item.href} onClick={() => go(item)} className="hover:text-[#151515] transition-colors uppercase tracking-wider">
                  {item.label}
                </button>
              ),
            )}
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
              {ctaLabel} <ArrowRight size={14} />
            </button>
          </div>
          <button className="md:hidden" onClick={() => setMenuOpen(!menuOpen)} aria-label="Open menu">
            {menuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
        {menuOpen && (
          <div className="md:hidden px-6 pb-4 flex flex-col gap-3 text-xs font-medium uppercase tracking-wider text-[#6B6459]">
            {nav.map((item) =>
              item.type === "hash" ? (
                <a key={item.href} href={item.href} onClick={() => setMenuOpen(false)}>
                  {item.label}
                </a>
              ) : (
                <button key={item.href} onClick={() => go(item)} className="text-left uppercase tracking-wider">
                  {item.label}
                </button>
              ),
            )}
            {!user && (
              <button onClick={() => navigate("/login")} className="text-left">
                Sign in
              </button>
            )}
            <button
              onClick={() => navigate(primaryCtaTarget)}
              className="font-bold px-4 py-2 rounded mt-1"
              style={{ backgroundColor: "#D97B29", color: "#1C1206" }}
            >
              {ctaLabel}
            </button>
          </div>
        )}
      </header>

      {children}

      <footer className="border-t border-[#E7E5DE] py-8">
        <div className="max-w-6xl mx-auto px-6 flex flex-col sm:flex-row gap-3 sm:items-center sm:justify-between text-xs text-[#9C9488]">
          <span>© 2026 Flywheel</span>
          <div className="flex gap-5">
            <button onClick={() => navigate("/")} className="hover:text-[#151515]">
              Product
            </button>
            <button onClick={() => navigate("/lawyers")} className="hover:text-[#151515]">
              For attorneys
            </button>
            <span>Deterministic by design</span>
          </div>
        </div>
      </footer>

      {!user && (
        <div
          className="md:hidden fixed bottom-0 inset-x-0 z-30 p-3"
          style={{ background: "linear-gradient(to top, #F5F1EA 70%, #F5F1EA00)" }}
        >
          <button
            onClick={() => navigate(primaryCtaTarget)}
            className="w-full text-sm font-bold uppercase tracking-wide px-5 py-3 rounded flex items-center justify-center gap-2 shadow-sm"
            style={{ backgroundColor: "#D97B29", color: "#1C1206" }}
          >
            Start 7-day free trial <ArrowRight size={15} />
          </button>
        </div>
      )}
    </div>
  );
}

export function usePrimaryCta() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const target = user ? (user.business_ids.length > 0 ? "/app" : "/onboarding") : "/signup";
  return { navigate, user, target };
}
