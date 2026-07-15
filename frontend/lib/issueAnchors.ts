import type { BlockingIssue, IssueAnchor } from "@/lib/api";

export type EntryIssueSeverity = "minor" | "urgent" | "critical";

export interface EntryIssueBadge {
  count: number;
  severity: EntryIssueSeverity;
}

const IMPACT_TO_SEVERITY: Record<BlockingIssue["impact"], EntryIssueSeverity> = {
  high: "critical",
  medium: "urgent",
  low: "minor",
};

const SEVERITY_RANK: Record<EntryIssueSeverity, number> = {
  minor: 0,
  urgent: 1,
  critical: 2,
};

export function entryAnchorKey(section: IssueAnchor["section"], entryIndex: number): string {
  return `${section}:${entryIndex}`;
}

export function resumeAnchorDomId(anchor: Pick<IssueAnchor, "section" | "entry_index">): string {
  return `resume-anchor-${anchor.section}-${anchor.entry_index}`;
}

export function summarizeEntryIssueBadges(
  issues: BlockingIssue[],
): Record<string, EntryIssueBadge> {
  const summary: Record<string, EntryIssueBadge> = {};
  for (const issue of issues) {
    if (!issue.anchor) continue;
    const key = entryAnchorKey(issue.anchor.section, issue.anchor.entry_index);
    const severity = IMPACT_TO_SEVERITY[issue.impact];
    const existing = summary[key];
    if (!existing) {
      summary[key] = { count: 1, severity };
      continue;
    }
    summary[key] = {
      count: existing.count + 1,
      severity:
        SEVERITY_RANK[severity] > SEVERITY_RANK[existing.severity]
          ? severity
          : existing.severity,
    };
  }
  return summary;
}

export function scrollToResumeAnchor(anchor: IssueAnchor): boolean {
  const el = document.getElementById(
    resumeAnchorDomId({ section: anchor.section, entry_index: anchor.entry_index }),
  );
  if (!el) return false;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("ring-2", "ring-amber-400/70", "ring-offset-2", "ring-offset-slate-900");
  window.setTimeout(() => {
    el.classList.remove("ring-2", "ring-amber-400/70", "ring-offset-2", "ring-offset-slate-900");
  }, 1800);
  return true;
}
