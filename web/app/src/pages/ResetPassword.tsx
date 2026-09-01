import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { Field, inputCls } from "../components/Shared";

export default function ResetPassword() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const token = params.get("token");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    // The bearer token is needed once, never left in browser history after a
    // completed/invalid attempt.
    if (!token) setError("This reset link is invalid or has expired.");
  }, [token]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token) return;
    if (password.length < 12) { setError("Use at least 12 characters."); return; }
    if (password !== confirm) { setError("Passwords do not match."); return; }
    setSubmitting(true); setError(null);
    try {
      await api.resetPassword(token, password);
      setParams({}, { replace: true });
      navigate("/login", { replace: true });
    } catch (err) {
      setParams({}, { replace: true });
      setError(err instanceof ApiError ? "This reset link is invalid or has expired." : "Couldn’t reset your password.");
    } finally { setSubmitting(false); }
  }

  return <div style={{ backgroundColor: "#F5F1EA", color: "#151515" }} className="min-h-screen flex items-center justify-center px-6"><div className="w-full max-w-sm bg-white rounded-2xl border border-[#E7E5DE] p-7"><h1 className="text-2xl mb-2">Choose a new password</h1><p className="text-sm text-[#6B6459] mb-6">This link can be used once. Other signed-in sessions will be ended.</p>{token ? <form onSubmit={submit}><Field label="New password"><input type="password" required className={inputCls} value={password} onChange={(e) => setPassword(e.target.value)} /></Field><Field label="Confirm password"><input type="password" required className={inputCls} value={confirm} onChange={(e) => setConfirm(e.target.value)} /></Field>{error && <p className="text-sm text-[#B4483A] mb-4">{error}</p>}<button disabled={submitting} className="w-full text-sm font-medium text-white px-5 py-2.5 rounded-lg disabled:opacity-60" style={{ backgroundColor: "#151515" }}>{submitting ? "Saving…" : "Set new password"}</button></form> : <Link to="/forgot-password" className="text-sm font-medium" style={{ color: "#B87333" }}>Request a new link</Link>}</div></div>;
}
