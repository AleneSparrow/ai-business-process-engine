import type { ComponentType, ReactNode } from "react";
import type { ProcessState } from "../api/client";

/**
 * Design-system primitives ported directly from the prototype (atelierprototype.jsx --
 * a historical filename from before the Flywheel rebrand, not a brand reference),
 * kept pixel-for-pixel so Dashboard/Conversation/Settings still read as one product.
 */

/**
 * The five steps of the DEAL, in the owner's words -- this is what the
 * "Where this case is" stepper shows.
 *
 * It used to read Trigger / Context / Decision / Action / Result. Those are
 * the engine's five phases for processing ONE MESSAGE (arrived, understood,
 * decided, replied, state written), which is a debugging view: every message
 * walks all five, so the stepper told the owner nothing about the deal and
 * the audit trail looked like the same four lines on a loop. The owner's
 * question is never "which phase is this message in", it is "where is this
 * deal". The indices below are unchanged -- mapProcessState already derived
 * them from the CASE state, not from events, so only the words were wrong.
 */
export const STAGES = ["New", "Contacted", "Qualified", "Booked", "Completed"];

export type CaseState = "NEW" | "QUALIFYING" | "NEEDS_HUMAN" | "BOOKED" | "LOST" | "COMPLETED";

// QUALIFYING deliberately uses the brand's functional accent (amber, not the
// bronze brand accent) -- per the brand book, amber is reserved for
// "active, in motion" product states, and a case being actively qualified
// is exactly that. Every other state here is a resting/terminal state.
export const STATE_META: Record<CaseState, { label: string; color: string; bg: string }> = {
  NEW: { label: "New", color: "#6B6459", bg: "#F1F1EF" },
  QUALIFYING: { label: "Qualifying", color: "#D97B29", bg: "#FBF0E2" },
  NEEDS_HUMAN: { label: "Needs you", color: "#C97A1F", bg: "#FBF0E2" },
  BOOKED: { label: "Booked", color: "#1E7B52", bg: "#E9F5EF" },
  LOST: { label: "Lost", color: "#B4483A", bg: "#FBEBE9" },
  COMPLETED: { label: "Completed", color: "#151515", bg: "#F1F1EF" },
};

/**
 * The Flywheel emblem, simplified for UI use -- a rim, five spokes, a small
 * hub node, and a short motion-trail arc (per the brand-book revision: five
 * spokes, not three or four -- three in a ring reads instantly as a
 * well-known automotive badge, a collision the book deliberately designs
 * away from; five keeps the silhouette unmistakably a wheel while staying
 * clear of that association at every size, "legible at 16x16px"). Renders
 * in `currentColor` so it inherits whatever text color its container sets.
 */
export function FlywheelMark({ size = 16, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      aria-hidden="true"
      className={className}
    >
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="1.3" fill="currentColor" stroke="none" />
      <path d="M12 12 L13.9 4.8" />
      <path d="M12 12 L19.5 11.6" />
      <path d="M12 12 L14.7 19" />
      <path d="M12 12 L6.2 16.7" />
      <path d="M12 12 L5.7 7.9" />
      <path d="M20.3 9.3 A9 9 0 0 1 21.2 12.6" strokeWidth="1.2" opacity="0.55" />
    </svg>
  );
}

/**
 * The real engine has more states than the UI's simplified five-bucket view
 * (`src/domain/states.py::ProcessState`) — this collapses them for display.
 * Also returns a 0–4 "stage" index into STAGES for the progress dots; this is
 * an approximation for the visual, not something the backend tracks directly.
 */
export function mapProcessState(state: ProcessState): { caseState: CaseState; stage: number } {
  switch (state) {
    case "NEW_LEAD":
      return { caseState: "NEW", stage: 0 };
    case "CONTACTED":
      return { caseState: "QUALIFYING", stage: 1 };
    case "QUALIFYING":
      return { caseState: "QUALIFYING", stage: 1 };
    case "QUALIFIED":
      return { caseState: "QUALIFYING", stage: 2 };
    case "NEEDS_HUMAN":
      return { caseState: "NEEDS_HUMAN", stage: 2 };
    case "BOOKED":
    case "QUOTED":
      return { caseState: "BOOKED", stage: 3 };
    case "FOLLOW_UP":
      return { caseState: "QUALIFYING", stage: 3 };
    case "WON":
    case "PAID":
      return { caseState: "BOOKED", stage: 3 };
    case "COMPLETED":
    case "REVIEW_REQUESTED":
      return { caseState: "COMPLETED", stage: 4 };
    case "REACTIVATION":
      return { caseState: "QUALIFYING", stage: 1 };
    case "LOST":
    case "CANCELLED":
      return { caseState: "LOST", stage: 2 };
    default:
      return { caseState: "NEW", stage: 0 };
  }
}

/**
 * event_type -> (what kind of step it was, human-readable summary) for the
 * audit trail.
 *
 * `stage` here is deliberately NOT the deal stage above -- it says what the
 * engine DID on that line. It used to borrow the old Trigger/Context/
 * Decision/Action/Result words, which made the audit trail read like
 * engineering telemetry; these are the same distinctions in plain English.
 */
const EVENT_TYPE_META: Record<string, { stage: string; label: string }> = {
  TRIGGER_RECEIVED: { stage: "Received", label: "Inbound message received" },
  LEAD_INTAKE_RECEIVED: { stage: "Received", label: "Lead intake received" },
  INTENT_EXTRACTED: { stage: "Understood", label: "Customer intent understood" },
  QUALIFICATION_EVALUATED: { stage: "Decided", label: "Qualification evaluated" },
  DECISION_RECORDED: { stage: "Decided", label: "Decision recorded" },
  CUSTOMER_RESPONSE_CREATED: { stage: "Replied", label: "Reply sent to customer" },
  STATE_CHANGED: { stage: "Updated", label: "Case moved to a new stage" },
  TRANSITION_REJECTED: { stage: "Updated", label: "Transition rejected" },
  DUPLICATE_IGNORED: { stage: "Updated", label: "Duplicate message ignored" },
  LEAD_QUALIFICATION_TRANSITION: { stage: "Decided", label: "Qualification stage updated" },
  HUMAN_REPLY_SENT: { stage: "Replied", label: "Staff replied to customer" },
  PAYMENT_REQUEST_CREATED: { stage: "Updated", label: "Payment request prepared" },
  PAYMENT_RECORDED: { stage: "Updated", label: "Customer payment recorded" },
  BOOKING_COMPLETED: { stage: "Updated", label: "Appointment marked complete" },
  SERVICE_COMPLETED: { stage: "Updated", label: "Work marked complete" },
  REVIEW_REQUEST_SENT: { stage: "Replied", label: "Review request sent" },
};

export function describeEvent(eventType: string): { stage: string; label: string } {
  return EVENT_TYPE_META[eventType] ?? { stage: "Event", label: eventType };
}

/** "2m ago" / "3h ago" / "5d ago" style relative time from an ISO timestamp. */
export function formatRelativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diffSeconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (diffSeconds < 60) return "just now";
  const diffMinutes = Math.round(diffSeconds / 60);
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.round(diffHours / 24);
  return `${diffDays}d ago`;
}

/**
 * Dots and their captions share ONE grid, so a caption always sits under its
 * own dot. They used to be two independent rows -- fixed-width dots packed
 * left, captions spread across the full width with justify-between -- which
 * only looked aligned while the words were as short as "Trigger" and
 * "Result". With the real deal stages ("Contacted", "Completed") the two rows
 * visibly disagreed about which step was which.
 *
 * Pass `labels` on the detail panels; the list rows want the dots alone.
 */
export function Stepper({ stage, color = "#B87333", labels = false }: {
  stage: number;
  color?: string;
  labels?: boolean;
}) {
  const columns = { gridTemplateColumns: `repeat(${STAGES.length}, minmax(0, 1fr))` };
  return (
    <div className="w-full">
      <div className="grid items-center" style={columns}>
        {STAGES.map((label, i) => (
          <div key={label} className="flex items-center min-w-0">
            <div
              className="w-2 h-2 rounded-full shrink-0"
              style={{
                backgroundColor: i <= stage ? color : "#DEDBD2",
                boxShadow: i === stage ? `0 0 0 3px ${color}22` : "none",
              }}
              title={label}
            />
            {i < STAGES.length - 1 && (
              <div className="h-px flex-1 mx-1.5" style={{ backgroundColor: i < stage ? color : "#DEDBD2" }} />
            )}
          </div>
        ))}
      </div>
      {labels && (
        <div className="grid mt-1.5" style={columns}>
          {STAGES.map((label) => (
            <span key={label} className="text-[10px] leading-tight text-[#9C9488] break-words pr-1">{label}</span>
          ))}
        </div>
      )}
    </div>
  );
}

export function StatePill({ state }: { state: CaseState }) {
  const m = STATE_META[state];
  return (
    <span
      className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium"
      style={{ color: m.color, backgroundColor: m.bg }}
    >
      {m.label}
    </span>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="mb-5">
      <label className="block text-sm font-medium mb-1.5">{label}</label>
      {hint && <p className="text-xs text-[#9C9488] mb-2">{hint}</p>}
      {children}
    </div>
  );
}

export const inputCls =
  "w-full px-3.5 py-2.5 rounded-lg border border-[#E7E5DE] bg-white text-sm outline-none focus:ring-2 focus:ring-[#B8733333] focus:border-[#B87333] transition-shadow";

/** Used on both Onboarding's "Who can you serve?" step and Settings' "Service
 * area" tab, so a remote/local choice looks and behaves identically wherever
 * it's edited. */
export function AreaOption({
  icon: Icon,
  label,
  desc,
  active,
  onClick,
}: {
  // lucide-react icons type `size` as `string | number`, not just `number` --
  // widened to match so passing Globe/MapPin here type-checks under `tsc -b`
  // (this prop previously only worked because it was never actually built
  // with project-reference mode; `npm run dev` doesn't run this check).
  icon: ComponentType<{ size?: number | string }>;
  label: string;
  desc: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-left p-4 rounded-xl border transition-colors flex flex-col gap-2.5"
      style={{ borderColor: active ? "#B87333" : "#E7E5DE", backgroundColor: active ? "#F5E7D6" : "#fff" }}
    >
      <div
        className="w-8 h-8 rounded-lg flex items-center justify-center"
        style={{ backgroundColor: active ? "#B87333" : "#F1F1EF", color: active ? "#fff" : "#6B6459" }}
      >
        <Icon size={15} />
      </div>
      <div>
        <div className="text-sm font-medium mb-0.5">{label}</div>
        <div className="text-xs text-[#6B6459] leading-relaxed">{desc}</div>
      </div>
    </button>
  );
}

export function ToneOption({
  label,
  desc,
  active,
  onClick,
}: {
  label: string;
  desc: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-left px-4 py-3 rounded-xl border transition-colors"
      style={{ borderColor: active ? "#B87333" : "#E7E5DE", backgroundColor: active ? "#F5E7D6" : "#fff" }}
    >
      <div className="text-sm font-medium mb-0.5">{label}</div>
      <div className="text-xs text-[#6B6459]">{desc}</div>
    </button>
  );
}

/** Shown on preview-data screens (Dashboard/Conversation/Settings) until the staff
 * dashboard/conversation API (Milestone 8 slice 2) exists. Keeps the prototype's
 * mock content honest instead of implying it's live. */
export function PreviewBanner({ text }: { text: string }) {
  return (
    <div
      className="px-4 py-2.5 text-xs font-medium flex items-center gap-2"
      style={{ backgroundColor: "#FBF0E2", color: "#8A5A17", borderBottom: "1px solid #E7E5DE" }}
    >
      {text}
    </div>
  );
}
