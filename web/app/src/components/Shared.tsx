import type { ReactNode } from "react";

/**
 * Design-system primitives ported directly from the prototype (atelierprototype.jsx),
 * kept pixel-for-pixel so Dashboard/Conversation/Settings still read as one product.
 */

export const STAGES = ["Trigger", "Context", "Decision", "Action", "Result"];

export type CaseState = "NEW" | "QUALIFYING" | "NEEDS_HUMAN" | "BOOKED" | "LOST" | "COMPLETED";

export const STATE_META: Record<CaseState, { label: string; color: string; bg: string }> = {
  NEW: { label: "New", color: "#6B7280", bg: "#F1F1EF" },
  QUALIFYING: { label: "Qualifying", color: "#3A3EA6", bg: "#EEEEF9" },
  NEEDS_HUMAN: { label: "Needs you", color: "#C97A1F", bg: "#FBF0E2" },
  BOOKED: { label: "Booked", color: "#1E7B52", bg: "#E9F5EF" },
  LOST: { label: "Lost", color: "#B4483A", bg: "#FBEBE9" },
  COMPLETED: { label: "Completed", color: "#171A21", bg: "#F1F1EF" },
};

export function Stepper({ stage, color = "#3A3EA6" }: { stage: number; color?: string }) {
  return (
    <div className="flex items-center gap-1.5">
      {STAGES.map((label, i) => (
        <div key={label} className="flex items-center gap-1.5">
          <div
            className="w-2 h-2 rounded-full"
            style={{
              backgroundColor: i <= stage ? color : "#DEDBD2",
              boxShadow: i === stage ? `0 0 0 3px ${color}22` : "none",
            }}
            title={label}
          />
          {i < STAGES.length - 1 && (
            <div className="h-px w-4" style={{ backgroundColor: i < stage ? color : "#DEDBD2" }} />
          )}
        </div>
      ))}
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
      {hint && <p className="text-xs text-[#9AA1AC] mb-2">{hint}</p>}
      {children}
    </div>
  );
}

export const inputCls =
  "w-full px-3.5 py-2.5 rounded-lg border border-[#E7E5DE] bg-white text-sm outline-none focus:ring-2 focus:ring-[#3A3EA633] focus:border-[#3A3EA6] transition-shadow";

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
      style={{ borderColor: active ? "#3A3EA6" : "#E7E5DE", backgroundColor: active ? "#EEEEF9" : "#fff" }}
    >
      <div className="text-sm font-medium mb-0.5">{label}</div>
      <div className="text-xs text-[#6B7280]">{desc}</div>
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
