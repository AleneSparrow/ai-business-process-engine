import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useAuth, describeError } from "../auth/AuthContext";
import { Field, FlywheelMark, inputCls } from "../components/Shared";

export default function Login() {
  const navigate = useNavigate();
  const { login, completeTwoFactorLogin } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [challenge, setChallenge] = useState<string | null>(null);
  const [twoFactorCode, setTwoFactorCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await login(email.trim(), password);
      if ("two_factor_required" in result) {
        setChallenge(result.challenge_token);
        return;
      }
      const user = result;
      navigate(user.business_ids.length > 0 ? "/app" : "/onboarding");
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleTwoFactor(event: FormEvent) {
    event.preventDefault();
    if (!challenge) return;
    setError(null);
    setSubmitting(true);
    try {
      const user = await completeTwoFactorLogin(challenge, twoFactorCode);
      navigate(user.business_ids.length > 0 ? "/app" : "/onboarding");
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{ backgroundColor: "#F5F1EA", fontFamily: "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif", color: "#151515" }} className="min-h-screen w-full flex items-center justify-center px-6">
      <div className="w-full max-w-sm">
        <Link to="/lawyers" className="flex items-center gap-2 mb-8 justify-center">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center text-white"
            style={{ backgroundColor: "#B87333" }}
          >
            <FlywheelMark size={16} />
          </div>
          <span className="font-semibold text-sm" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif" }}>Flywheel</span>
        </Link>

        <div className="bg-white rounded-2xl border border-[#E7E5DE] p-7">
          <h1 className="text-2xl mb-1.5" style={{ fontFamily: "'Century Gothic', 'Futura', 'Trebuchet MS', sans-serif", fontWeight: 600 }}>
            Sign in
          </h1>
          <p className="text-sm text-[#6B6459] mb-6">Welcome back — your engine kept working while you were away.</p>

          {!challenge ? <form onSubmit={handleSubmit}>
            <Field label="Work email">
              <input
                type="email"
                required
                autoFocus
                className={inputCls}
                placeholder="you@yourbusiness.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </Field>
            <Field label="Password">
              <input
                type="password"
                required
                className={inputCls}
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
            <div className="-mt-2 mb-5 text-right">
              <Link to="/forgot-password" className="text-xs font-medium" style={{ color: "#B87333" }}>
                Forgot password?
              </Link>
            </div>

            {error && (
              <div className="mb-4 text-sm px-3.5 py-2.5 rounded-lg" style={{ color: "#B4483A", backgroundColor: "#FBEBE9" }}>
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="w-full text-sm font-medium text-white px-5 py-2.5 rounded-lg flex items-center justify-center gap-1.5 disabled:opacity-60"
              style={{ backgroundColor: "#151515" }}
            >
              {submitting ? "Signing in…" : "Sign in"} <ArrowRight size={14} />
            </button>
          </form> : <form onSubmit={handleTwoFactor}>
            <p className="text-sm text-[#6B6459] mb-5">Enter the six-digit code from your authenticator app, or a recovery code.</p>
            <Field label="Authenticator or recovery code">
              <input type="text" required autoFocus className={inputCls} value={twoFactorCode} onChange={(e) => setTwoFactorCode(e.target.value)} autoComplete="one-time-code" />
            </Field>
            {error && <div className="mb-4 text-sm px-3.5 py-2.5 rounded-lg" style={{ color: "#B4483A", backgroundColor: "#FBEBE9" }}>{error}</div>}
            <button type="submit" disabled={submitting} className="w-full text-sm font-medium text-white px-5 py-2.5 rounded-lg disabled:opacity-60" style={{ backgroundColor: "#151515" }}>
              {submitting ? "Verifying…" : "Verify and sign in"}
            </button>
          </form>}
        </div>

        <p className="text-sm text-[#6B6459] text-center mt-5">
          New to Flywheel?{" "}
          <Link to="/signup" className="font-medium" style={{ color: "#B87333" }}>
            Create an account
          </Link>
        </p>
      </div>
    </div>
  );
}
