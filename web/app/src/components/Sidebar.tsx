import { useEffect, useState, type ComponentType } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { LayoutGrid, MessageSquare, Workflow, CreditCard, LogOut } from "lucide-react";
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
  );
}
