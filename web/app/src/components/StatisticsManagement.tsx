import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type ReportingSettings } from "../api/client";
import { describeError, useAuth } from "../auth/AuthContext";

/** Reset / restore the selected business's dashboard metrics.
 * Lives on the personal account so owners do not have to hunt for it in
 * Overview or Settings. Conversations and audit history are never deleted. */
export function StatisticsManagement() {
  const navigate = useNavigate();
  const { token, businessId } = useAuth();
  const [reporting, setReporting] = useState<ReportingSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmingReset, setConfirmingReset] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!token || !businessId) {
      setReporting(null);
      return;
    }
    setError(null);
    api
      .getReportingSettings(token, businessId)
      .then((value) => {
        if (!cancelled) setReporting(value);
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err));
      });
    return () => {
      cancelled = true;
    };
  }, [token, businessId]);

  async function update(update: Parameters<typeof api.updateReportingSettings>[2]) {
    if (!token || !businessId) return;
    setSaving(true);
    setError(null);
    try {
      setReporting(await api.updateReportingSettings(token, businessId, update));
      setConfirmingReset(false);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  if (!businessId) {
    return (
      <section className="max-w-2xl border border-[#E7E5DE] bg-white rounded-xl p-5 sm:p-6 mb-10">
        <h2 className="text-lg font-semibold">Statistics</h2>
        <p className="text-sm text-[#6B6459] mt-1">
          Select a business in the sidebar to reset or restore its dashboard metrics.
        </p>
      </section>
    );
  }

  const baselineLabel = reporting?.stats_since
    ? `Counting cases created since ${new Date(reporting.stats_since).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" })}`
    : "Counting all retained history";

  return (
    <section className="max-w-2xl border border-[#E7E5DE] bg-white rounded-xl p-5 sm:p-6 mb-10">
      <h2 className="text-lg font-semibold">Statistics</h2>
      <p className="text-sm text-[#6B6459] mt-1 mb-5 leading-relaxed">
        These controls apply to the business currently selected in the sidebar. Resetting starts dashboard metrics from now. It never deletes conversations, cases, or audit events.
      </p>
      {reporting?.test_mode_enabled && (
        <div className="rounded-lg border p-4 mb-5" style={{ borderColor: "#E8CFAF", backgroundColor: "#FFF8EE" }}>
          <p className="text-sm font-medium text-[#8A561B]">Test mode is on.</p>
          <p className="text-sm text-[#6B6459] mt-1">New conversations are not counted in statistics.</p>
          <button
            type="button"
            onClick={() => navigate("/app/settings?tab=widget")}
            className="text-sm font-medium text-[#151515] underline mt-2"
          >
            Change it in Settings → Install widget
          </button>
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm px-3 py-2 mb-4 rounded bg-[#FBEBE9] text-[#B4483A]">
          {error}
        </p>
      )}
      <p className="text-xs text-[#6B6459]" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>
        {reporting ? baselineLabel : "Loading…"}
      </p>
      <div className="flex flex-wrap gap-2 mt-4">
        {confirmingReset ? (
          <>
            <button
              type="button"
              onClick={() => void update({ reset_statistics: true })}
              disabled={!reporting || saving}
              className="text-sm font-medium px-4 py-2.5 rounded-lg border border-[#C97A1F] text-[#8A561B] bg-[#FFF9F2] disabled:opacity-50"
            >
              {saving ? "Resetting…" : "Confirm reset"}
            </button>
            <button
              type="button"
              onClick={() => setConfirmingReset(false)}
              disabled={saving}
              className="text-sm font-medium px-4 py-2.5 rounded-lg border border-[#E7E5DE] disabled:opacity-50"
            >
              Cancel
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={() => setConfirmingReset(true)}
            disabled={!reporting || saving}
            className="text-sm font-medium px-4 py-2.5 rounded-lg border border-[#E7E5DE] disabled:opacity-50"
          >
            Reset statistics
          </button>
        )}
        {reporting?.stats_since && (
          <button
            type="button"
            onClick={() => void update({ clear_statistics_baseline: true })}
            disabled={saving}
            className="text-sm font-medium px-4 py-2.5 rounded-lg border border-[#E7E5DE] disabled:opacity-50"
          >
            Restore full history
          </button>
        )}
      </div>
    </section>
  );
}
