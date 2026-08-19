import type { EntryIssueBadge, EntryIssueSeverity } from "@/lib/issueAnchors";

const SEVERITY_STYLES: Record<EntryIssueSeverity, string> = {
  minor: "bg-slate-600/40 text-slate-700 dark:text-slate-300 border-slate-400 dark:border-slate-600",
  urgent: "bg-amber-500/15 dark:bg-amber-400/15 text-amber-700 dark:text-amber-300 border-amber-400/30",
  critical: "bg-red-400/15 text-red-700 dark:text-red-300 border-red-400/30",
};

export function EntryIssueBadgePill({ badge }: { badge: EntryIssueBadge }) {
  return (
    <span
      className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide border ${SEVERITY_STYLES[badge.severity]}`}
      title={`${badge.count} ATS issue${badge.count === 1 ? "" : "s"} on this entry`}
    >
      {badge.count} issue{badge.count === 1 ? "" : "s"}
    </span>
  );
}
