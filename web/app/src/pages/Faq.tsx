import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Menu, X } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { FaqSection } from "../components/FaqSection";
import { FlywheelMark } from "../components/Shared";

/** Dedicated FAQ page so signed-in owners can open the answers from the
 * cabinet without hunting through the marketing homepage hash. Public, same
 * chrome as the landing page: logo returns to `/`, CTA returns to the app. */
export default function Faq() {
  const [menuOpen, setMenuOpen] = useState(false);
  const navigate = useNavigate();
  const { user } = useAuth();
  const primaryCtaTarget = user ? (user.business_ids.length > 0 ? "/app" : "/onboarding") : "/signup";

  return (
    <div style={{ backgroundColor: "#F5F1EA", fontFamily: "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif", color: "#151515" }} className="min-h-screen w-full">
      <header className="sticky top-0 z-20 backdrop-blur-sm" style={{ backgroundColor: "#F5F1EAEE", borderBottom: "1px solid #E7E5DE" }}>
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <button onClick={() => navigate("/")} className="flex items-center gap-2">
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center text-white"
              style={{ backgroundColor: "#B87333" }}
            >
              <FlywheelMark size={16} />
            </div>
            <span className="font-semibold text-sm" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif" }}>
              Flywheel
            </span>
          </button>
          <nav className="hidden md:flex items-center gap-8 text-xs font-medium uppercase tracking-wider text-[#6B6459]">
            <a href="/#how" className="hover:text-[#151515] transition-colors">How it works</a>
            <a href="/#features" className="hover:text-[#151515] transition-colors">Features</a>
            <a href="/#trust" className="hover:text-[#151515] transition-colors">Trust & audit</a>
            <span className="text-[#151515]">FAQ</span>
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
              {user ? "Go to dashboard" : "Get started"} <ArrowRight size={14} />
            </button>
          </div>
          <button className="md:hidden" onClick={() => setMenuOpen(!menuOpen)}>
            {menuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
        {menuOpen && (
          <div className="md:hidden px-6 pb-4 flex flex-col gap-3 text-xs font-medium uppercase tracking-wider text-[#6B6459]">
            <a href="/#how">How it works</a>
            <a href="/#features">Features</a>
            <a href="/#trust">Trust & audit</a>
            <span className="text-[#151515]">FAQ</span>
            {!user && (
              <button onClick={() => navigate("/login")} className="text-left">Sign in</button>
            )}
            <button onClick={() => navigate(primaryCtaTarget)} className="font-bold px-4 py-2 rounded mt-1" style={{ backgroundColor: "#D97B29", color: "#1C1206" }}>
              {user ? "Go to dashboard" : "Get started"}
            </button>
          </div>
        )}
      </header>

      <FaqSection headingLevel="h1" standalone />

      <footer className="border-t border-[#E7E5DE] py-8">
        <div className="max-w-6xl mx-auto px-6 flex items-center justify-between text-xs text-[#9C9488]">
          <span>© 2026 Flywheel</span>
          <button onClick={() => navigate("/")} className="hover:text-[#151515] transition-colors">
            Back to home
          </button>
        </div>
      </footer>
    </div>
  );
}
