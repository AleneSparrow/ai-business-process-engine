import { useEffect, useState, type ComponentType } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { LayoutGrid, MessageSquare, Workflow, CreditCard, LogOut, Menu, X, Plus, Check, ChevronsUpDown, Home, HelpCircle } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { api, type OwnedBusiness } from "../api/client";
import { FlywheelMark } from "./Shared";

/** Dropdown for switching between the account's businesses -- only rendered
 * when there's more than one (see Sidebar). Also offers "Add another
 * business", the entry point back into /onboarding now that it's reachable
 * any time (see App.tsx). */
function BusinessSwitcher({
  businesses,
  activeId,
  onSelect,
  onAddBusiness,
}: {
  businesses: OwnedBusiness[];
  activeId: string | null;
  onSelect: (businessId: string) => void;
  onAddBusiness: () => void;
}) {
  const [open, setOpen] = useState(false);
  const active = businesses.find((b) => b.business_id === activeId);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-1.5 text-left"
      >
        <div className="min-w-0">
          <div className="text-sm font-semibold leading-tight truncate">{active?.name ?? "Your business"}</div>
        </div>
        <ChevronsUpDown size={13} className="shrink-0" style={{ color: "#9C9488" }} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute left-0 right-0 top-full mt-1.5 z-50 bg-white rounded-lg border border-[#E7E5DE] shadow-lg py-1.5 overflow-hidden">
            {businesses.map((b) => (
              <button
                key={b.business_id}
                onClick={() => {
                  setOpen(false);
                  if (b.business_id !== activeId) onSelect(b.business_id);
                }}
                className="w-full flex items-center justify-between gap-2 px-3 py-2 text-sm text-left hover:bg-[#F5F1EA]"
                style={{ color: "#151515" }}
              >
                <span className="truncate">{b.name}</span>
                {b.business_id === activeId && <Check size={13} style={{ color: "#1E7B52" }} className="shrink-0" />}
              </button>
            ))}
            <div className="border-t border-[#F0EFE9] mt-1 pt-1">
              <button
                onClick={() => {
                  setOpen(false);
                  onAddBusiness();
                }}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-[#F5F1EA]"
                style={{ color: "#B87333" }}
              >
                <Plus size={13} className="shrink-0" /> Add another business
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

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
  businesses,
  businessId,
  businessName,
  email,
  onNavigate,
  onSelectBusiness,
  onLogout,
}: {
  view: "dashboard" | "conversation" | "settings" | "billing" | "account";
  businesses: OwnedBusiness[];
  businessId: string | null;
  businessName: string | null;
  email: string | undefined;
  onNavigate: (path: string) => void;
  onSelectBusiness: (businessId: string) => void;
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
              <div className="flex items-start justify-between mb-6 px-2 gap-2">
                <div className="min-w-0 flex-1">
                  {businesses.length > 1 ? (
                    <BusinessSwitcher
                      businesses={businesses}
                      activeId={businessId}
                      onSelect={(id) => {
                        setOpen(false);
                        onSelectBusiness(id);
                      }}
                      onAddBusiness={() => go("/onboarding")}
                    />
                  ) : (
                    <div className="text-sm font-semibold leading-tight truncate">{businessName ?? "Your business"}</div>
                  )}
                  <button
                    type="button"
                    aria-label="Open personal account"
                    onClick={() => go("/app/account")}
                    className="block max-w-full text-[11px] text-[#6B6459] leading-tight truncate rounded-sm hover:text-[#B87333] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B87333] focus-visible:ring-offset-2 transition-colors"
                  >
                    {email}
                  </button>
                </div>
                <button onClick={() => setOpen(false)} aria-label="Close menu" className="p-1 shrink-0" style={{ color: "#6B6459" }}>
                  <X size={18} />
                </button>
              </div>
              <nav className="flex flex-col gap-1">
                <NavItem icon={LayoutGrid} label="Overview" active={view === "dashboard"} onClick={() => go("/app")} />
                <NavItem icon={MessageSquare} label="Conversations" active={view === "conversation"} onClick={() => go("/app/conversations")} />
                <NavItem icon={Workflow} label="Settings" active={view === "settings"} onClick={() => go("/app/settings")} />
                <NavItem icon={CreditCard} label="Billing" active={view === "billing"} onClick={() => go("/app/billing")} />
                <NavItem icon={HelpCircle} label="FAQ" active={view === "account"} onClick={() => go("/app/account#faq")} />
                <NavItem icon={Plus} label="Add another business" active={false} onClick={() => go("/onboarding")} />
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
  const { user, token, businessId, selectBusiness, logout } = useAuth();
  const [businesses, setBusinesses] = useState<OwnedBusiness[]>([]);

  useEffect(() => {
    let cancelled = false;
    if (!token || !user || user.business_ids.length === 0) {
      setBusinesses([]);
      return;
    }
    api
      .listMyBusinesses(token)
      .then((list) => {
        if (!cancelled) setBusinesses(list);
      })
      .catch(() => {
        if (!cancelled) setBusinesses([]);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, user?.user_id, businessId]);

  const businessName = businesses.find((b) => b.business_id === businessId)?.name ?? null;

  const view = location.pathname.startsWith("/app/settings")
    ? "settings"
    : location.pathname.startsWith("/app/account")
      ? "account"
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
        businesses={businesses}
        businessId={businessId}
        businessName={businessName}
        email={user?.email}
        onNavigate={(path) => navigate(path)}
        onSelectBusiness={selectBusiness}
        onLogout={handleLogout}
      />
      <aside className="w-60 shrink-0 border-r border-[#E7E5DE] px-4 py-5 hidden md:flex md:flex-col justify-between">
        <div>
          <div className="flex items-center gap-2 px-2 mb-8">
            <button
              onClick={() => navigate("/app")}
              className="w-7 h-7 rounded-lg flex items-center justify-center text-white shrink-0"
              style={{ backgroundColor: "#B87333" }}
            >
              <FlywheelMark size={16} />
            </button>
            <div className="min-w-0 flex-1">
              {businesses.length > 1 ? (
                <BusinessSwitcher
                  businesses={businesses}
                  activeId={businessId}
                  onSelect={selectBusiness}
                  onAddBusiness={() => navigate("/onboarding")}
                />
              ) : (
                <button onClick={() => navigate("/app")} className="text-left w-full">
                  <div className="text-sm font-semibold leading-tight truncate">{businessName ?? "Your business"}</div>
                </button>
              )}
              <button
                type="button"
                aria-label="Open personal account"
                onClick={() => navigate("/app/account")}
                className="block max-w-full text-[11px] text-[#6B6459] leading-tight truncate rounded-sm hover:text-[#B87333] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B87333] focus-visible:ring-offset-2 transition-colors"
              >
                {user?.email}
              </button>
            </div>
          </div>
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
              label="Settings"
              active={view === "settings"}
              onClick={() => navigate("/app/settings")}
            />
            <NavItem icon={CreditCard} label="Billing" active={view === "billing"} onClick={() => navigate("/app/billing")} />
            <NavItem icon={HelpCircle} label="FAQ" active={view === "account"} onClick={() => navigate("/app/account#faq")} />
            <NavItem icon={Plus} label="Add another business" active={false} onClick={() => navigate("/onboarding")} />
          </nav>
        </div>
        <div>
          <NavItem icon={Home} label="Home page" active={false} onClick={() => navigate("/")} />
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
