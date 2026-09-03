import { useEffect, useState, type FormEvent } from "react";
import { LogOut } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { describeError, useAuth } from "../auth/AuthContext";
import { AccountSecurityPanel } from "../components/AccountSecurityPanel";
import { FaqList } from "../components/FaqSection";
import { Field, inputCls } from "../components/Shared";
import { Sidebar } from "../components/Sidebar";

export default function Account() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, token, setUser, logout } = useAuth();
  const [name, setName] = useState(user?.name ?? "");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setName(user?.name ?? ""), [user?.name]);

  useEffect(() => {
    if (location.hash !== "#faq") return;
    document.getElementById("faq")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [location.hash]);

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    if (!token) return;
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const updated = await api.updateProfile(token, name);
      setUser(updated);
      setName(updated.name ?? "");
      setMessage("Your name was saved successfully.");
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  async function signOut() {
    await logout();
    navigate("/", { replace: true });
  }

  return (
    <div className="min-h-screen flex" style={{ backgroundColor: "#FAF9F6", color: "#151515" }}>
      <Sidebar />
      <main className="flex-1 min-w-0 pt-14 md:pt-0">
        <div className="max-w-3xl mx-auto px-5 sm:px-8 py-10 md:py-12">
          <div className="mb-9">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#B87333]">Personal account</p>
            <h1 className="text-3xl font-semibold tracking-tight mt-2">Your account</h1>
            <p className="text-sm text-[#6B6459] mt-2">Manage your personal details and account security.</p>
          </div>

          <form onSubmit={saveProfile} className="max-w-2xl border border-[#E7E5DE] bg-white rounded-xl p-5 sm:p-6 mb-10">
            <h2 className="text-lg font-semibold">Profile</h2>
            <p className="text-sm text-[#6B6459] mt-1 mb-5">These details belong to you, not to the selected business.</p>
            {error && <p role="alert" className="text-sm px-3 py-2 mb-4 rounded bg-[#FBEBE9] text-[#B4483A]">{error}</p>}
            {message && <p role="status" className="text-sm px-3 py-2 mb-4 rounded bg-[#E9F5EF] text-[#1E7B52]">{message}</p>}
            <Field label="Name">
              <input className={inputCls} value={name} maxLength={120} required onChange={(event) => setName(event.target.value)} autoComplete="name" />
            </Field>
            <Field label="Email">
              <input className={`${inputCls} bg-[#F5F1EA] text-[#6B6459]`} value={user?.email ?? ""} readOnly autoComplete="email" />
            </Field>
            <button disabled={saving || !name.trim()} className="px-4 py-2 rounded-lg text-sm text-white disabled:opacity-50" style={{ backgroundColor: "#151515" }}>
              {saving ? "Saving…" : "Save changes"}
            </button>
          </form>

          {token && <AccountSecurityPanel token={token} />}

          <section id="faq" className="max-w-2xl border border-[#E7E5DE] bg-white rounded-xl p-5 sm:p-6 mt-10">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#B87333]">FAQ</p>
            <h2 className="text-lg font-semibold mt-2">What people ask before they start</h2>
            <p className="text-sm text-[#6B6459] mt-1 mb-2">Straight answers about what Flywheel does and does not do.</p>
            <FaqList />
          </section>

          <section className="max-w-2xl border-t border-[#E7E5DE] mt-10 pt-8">
            <h2 className="text-lg font-semibold">Sign out</h2>
            <p className="text-sm text-[#6B6459] mt-1 mb-4">End your current Flywheel session on this device.</p>
            <button onClick={() => void signOut()} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm border border-[#E7C6C1] text-[#B4483A] hover:bg-[#FBEBE9] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B4483A] transition-colors">
              <LogOut size={16} /> Sign out
            </button>
          </section>
        </div>
      </main>
    </div>
  );
}
