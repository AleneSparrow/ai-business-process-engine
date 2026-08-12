import { useEffect, useState, type ComponentType } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { LayoutGrid, MessageSquare, Workflow, Settings as SettingsIcon, LogOut } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { api } from "../api/client";

function NavItem({
  icon: Icon,
  label,
  active,
  onClick,
}: {
  icon: ComponentType<{ size?: number; strokeWidth?: number }>;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors text-left"
      style={{
        color: active ? "#171A21" : "#6B7280",
        backgroundColor: active ? "#EEEEF9" : "transparent",
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
            className="w-7 h-7 rounded-lg flex items-center justify-center text-white text-xs font-bold"
            style={{ backgroundColor: "#3A3EA6", fontFamily: "'Space Grotesk', sans-serif" }}
          >
            A
          </div>
          <div className="text-left">
            <div className="text-sm font-semibold leading-tight">{businessName ?? "Your business"}</div>
            <div className="text-[11px] text-[#6B7280] leading-tight">{user?.email}</div>
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
          <NavItem icon={SettingsIcon} label="Settings" active={false} onClick={() => navigate("/app/settings")} />
        </nav>
      </div>
      <div>
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-[#6B7280] hover:text-[#171A21] transition-colors"
        >
          <LogOut size={16} strokeWidth={2} /> Sign out
        </button>
        <div className="px-2 mt-3 text-[11px] text-[#9AA1AC] leading-relaxed">
          Every step your engine takes — logged, reversible, never silent.
        </div>
      </div>
    </aside>
  );
}
