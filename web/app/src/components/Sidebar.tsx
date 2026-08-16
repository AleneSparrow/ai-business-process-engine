import { useEffect, useState, type ComponentType } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { LayoutGrid, MessageSquare, Workflow, CreditCard, LogOut, Menu, X } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { api } from "../api/client";
import { FlywheelMark } from "./Shared";

function NavItem({
  icon: Icon,
  label,
  active,
  onClick,
}: {
  // size and strokeWidth are both `string | number` on lucide-react's own
  // prop type -- widened to match, same fix as AreaOption in Shared.tsx.
  icon: ComponentType<{ size?: number | string; strokeWidth?: number | string }>;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors text-left"
      style={{
        color: active ? "#151515" : "#6B6459",
        backgroundColor: active ? "#F5E7D6" : "transparent",
        fontWeight: active ? 600 : 500,
      }}
    >
      <Icon size={17} strokeWidth={2} />
      {label}
    </button>
  );
}

/** The app shell's nav is otherwise desktop-only (see the `aside` below) --
 * on a phone there was previously no way at all to reach another page once
 * RequireActiveSubscription (see RouteGuards.tsx) redirected a business
 * without billing access to /app/billing: no sidebar, no back button,
 * nothing. This renders as a fixed overlay so it doesn't disturb the
 * desktop flex layout in Dashboard/Conversation/Settings/Billing -- each of
 * those pages just needs `pt-14 md:pt-0` on its `<main>` to clear it. */
function MobileNav({
  view,
  businessName,
  email,
  onNavigate,
  onLogout,
}: {
  view: "dashboard" | "conversation" | "settings" | "billing";
  businessName: string | null;
  email: string | undefined;
  onNavigate: (path: string) => void;
  onLogout: () => void;
}) {
  const [open, setOpen] = useState(false);

  const go = (path: string) => {
    setOpen(false);
    onNavigate(path);
  };

  return (
    <div className="md:hidden">
      <div
        className="fixed top-0 inset-x-0 z-40 flex items-center justify-between px-4 border-b border-[#E7E5DE]"
        style={{ height: 56, backgroundColor: "#F5F1EA" }}
      >
        <button onClick={() => go("/app")} className="flex items-center gap-2 min-w-0">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center text-white shrink-0"
            style={{ backgroundColor: "#B87333" }}
          >
            <FlywheelMark size={16} />
          </div>
          <div className="text-left min-w-0">
            <div className="text-sm font-semibold leading-tight truncate">{businessName ?? "Your business"}</div>
          </div>
        </button>
        <button
          onClick={() => setOpen(true)}
          aria-label="Open menu"
          className="p-2 -mr-2 shrink-0"
          style={{ color: "#151515" }}
        >
          <Menu size={20} />
        </button>
      </div>

      {open && (
        <div className="fixed inset-0 z-50 flex">
          <div className="absolute inset-0 bg-black/30" onClick={() => setOpen(false)} />
          <div className="relative w-64 max-w-[80%] h-full bg-white px-4 py-5 flex flex-col justify-between shadow-xl">
            <div>
              <div className="flex items-center justify-between mb-6 px-2">
                <div className="min-w-0">
                  <div className="text-sm font-semibold leading-tight truncate">{businessName ?? "Your business"}</div>
                  <div className="text-[11px] text-[#6B6459] leading-tight truncate">{email}</div>
                </div>
                <button onClick={() => setOpen(false)} aria-label="Close menu" className="p-1 shrink-0" style={{ color: "#6B6459" }}>
                  <X size={18} />
                </button>
              </div>
              <nav className="flex flex-col gap-1">
                <NavItem icon={LayoutGrid} label="Overview" active={view === "dashboard"} onClick={() => go("/app")} />
                <NavItem icon={MessageSquare} label="Conversations" active={view === "conversation"} onClick={() => go("/app/conversations")} />
                <NavItem icon={Workflow} label="Business DNA" active={view === "settings"} onClick={() => go("/app/settings")} />
                <NavItem icon={CreditCard} label="Billing" active={view === "billing"} onClick={() => go("/app/billing")} />
              </nav>
            </div>
            <button
              onClick={() => {
                setOpen(false);
                onLogout();
              }}
              className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-[#6B6459]"
            >
              <LogOut size={16} strokeWidth={2} /> Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const [businessName, setBusinessName] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (user?.business_id) {
      api
        .getBusiness(user.business_id)
        .then((business) => {
          if (!cancelled) setBusinessName(business.name);
        })
        .catch(() => {
          if (!cancelled) setBusinessName(null);
        });
    }
    return () => {
      cancelled = true;
    };
  }, [user?.business_id]);

  const view = location.pathname.startsWith("/app/settings")
    ? "settings"
    : location.pathname.startsWith("/app/billing")
      ? "billing"
      : location.pathname.startsWith("/app/conversations")
        ? "conversation"
        : "dashboard";

  async function handleLogout() {
    await logout();
    navigate("/", { replace: true });
  }

  return (
    <>
      <MobileNav
        view={view}
        businessName={businessName}
        email={user?.email}
        onNavigate={(path) => navigate(path)}
        onLogout={handleLogout}
      />
      <aside className="w-60 shrink-0 border-r border-[#E7E5DE] px-4 py-5 hidden md:flex md:flex-col justify-between">
        <div>
          <button onClick={() => navigate("/app")} className="flex items-center gap-2 px-2 mb-8">
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center text-white"
              style={{ backgroundColor: "#B87333" }}
            >
              <FlywheelMark size={16} />
            </div>
            <div className="text-left">
              <div className="text-sm font-semibold leading-tight">{businessName ?? "Your business"}</div>
              <div className="text-[11px] text-[#6B6459] leading-tight">{user?.email}</div>
            </div>
          </button>
          <nav className="flex flex-col gap-1">
            <NavItem icon={LayoutGrid} label="Overview" active={view === "dashboard"} onClick={() => navigate("/app")} />
            <NavItem
              icon={MessageSquare}
              label="Conversations"
              active={view === "conversation"}
              onClick={() => navigate("/app/conversations")}
            />
            <NavItem
              icon={Workflow}
              label="Business DNA"
              active={view === "settings"}
              onClick={() => navigate("/app/settings")}
            />
            <NavItem icon={CreditCard} label="Billing" active={view === "billing"} onClick={() => navigate("/app/billing")} />
          </nav>
        </div>
        <div>
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-[#6B6459] hover:text-[#151515] transition-colors"
          >
            <LogOut size={16} strokeWidth={2} /> Sign out
          </button>
          <div className="px-2 mt-3 text-[11px] text-[#9C9488] leading-relaxed">
            Every step your engine takes — logged, reversible, never silent.
          </div>
        </div>
      </aside>
    </>
  );
}
