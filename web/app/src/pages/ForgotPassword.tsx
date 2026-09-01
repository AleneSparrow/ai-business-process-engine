import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { Field, FlywheelMark, inputCls } from "../components/Shared";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    try {
      await api.forgotPassword(email.trim());
    } finally {
      // The confirmation is intentionally identical for every valid email.
      setSubmitted(true);
      setSubmitting(false);
    }
  }

  return <div style={{ backgroundColor: "#F5F1EA", color: "#151515" }} className="min-h-screen flex items-center justify-center px-6">
    <div className="w-full max-w-sm bg-white rounded-2xl border border-[#E7E5DE] p-7">
      <Link to="/login" className="flex items-center gap-2 mb-8"><span className="w-7 h-7 rounded-lg flex items-center justify-center text-white" style={{ backgroundColor: "#B87333" }}><FlywheelMark size={16} /></span><span className="font-semibold text-sm">Flywheel</span></Link>
      <h1 className="text-2xl mb-2">Reset your password</h1>
      {submitted ? <><p className="text-sm text-[#6B6459] mb-6">If an account matches that email, a reset link will arrive shortly.</p><Link to="/login" className="text-sm font-medium" style={{ color: "#B87333" }}>Back to sign in</Link></> : <form onSubmit={submit}>
        <p className="text-sm text-[#6B6459] mb-6">Enter your work email. We’ll send a one-time reset link if it matches an account.</p>
        <Field label="Work email"><input type="email" required autoFocus className={inputCls} value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
        <button type="submit" disabled={submitting} className="w-full text-sm font-medium text-white px-5 py-2.5 rounded-lg disabled:opacity-60" style={{ backgroundColor: "#151515" }}>{submitting ? "Sending…" : "Send reset link"}</button>
      </form>}
    </div>
  </div>;
}
