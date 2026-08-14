import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useAuth, describeError } from "../auth/AuthContext";
import { Field, FlywheelMark, inputCls } from "../components/Shared";

export default function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const user = await login(email.trim(), password);
      navigate(user.business_id ? "/app" : "/onboarding");
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{ backgroundColor: "#F5F1EA", fontFamily: "'Inter', sans-serif", color: "#151515" }} className="min-h-screen w-full flex items-center justify-center px-6">
      <div className="w-full max-w-sm">
        <Link to="/" className="flex items-center gap-2 mb-8 justify-center">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center text-white"
            style={{ backgroundColor: "#B87333" }}
          >
            <FlywheelMark size={16} />
          </div>
          <span className="font-semibold text-sm" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>Flywheel</span>
        </Link>

        <div className="bg-white rounded-2xl border border-[#E7E5DE] p-7">
          <h1 className="text-2xl mb-1.5" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}>
            Sign in
          </h1>
          <p className="text-sm text-[#6B6459] mb-6">Welcome back — your engine kept working while you were away.</p>

          <form onSubmit={handleSubmit}>
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
          </form>
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
