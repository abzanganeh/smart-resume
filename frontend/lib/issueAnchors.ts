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

/**
 * Stable key for deduping issues. Anchored issues use bullet location so re-score
 * does not treat the same bullet as a brand-new item when suggestion text changes.
 */
export function issueKey(issue: BlockingIssue): string {
  if (issue.anchor) {
    const { section, entry_index, bullet_index } = issue.anchor;
    return `anchor:${section}:${entry_index}:${bullet_index ?? "x"}`;
  }
  return `${issue.category}|${issue.description}|${issue.suggestion}`;
}

export function bulletAnchorKey(
  section: IssueAnchor["section"],
  entryIndex: number,
  bulletIndex: number,
): string {
  return `anchor:${section}:${entryIndex}:${bulletIndex}`;
}

export function buildBulletAtsIssueMap(
  issues: BlockingIssue[],
): Record<string, BlockingIssue[]> {
  const map: Record<string, BlockingIssue[]> = {};
  for (const issue of issues) {
    if (!issue.anchor || issue.anchor.bullet_index === undefined) continue;
    const key = bulletAnchorKey(
      issue.anchor.section,
      issue.anchor.entry_index,
      issue.anchor.bullet_index,
    );
    const bucket = map[key];
    if (bucket) {
      bucket.push(issue);
    } else {
      map[key] = [issue];
    }
  }
  return map;
}

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

const SCROLL_HIGHLIGHT_CLASSES = [
  "ring-2",
  "ring-amber-400/70",
  "ring-offset-2",
  "ring-offset-white",
  "dark:ring-offset-slate-900",
] as const;

export function scrollToResumeAnchor(anchor: IssueAnchor): boolean {
  const el = document.getElementById(
    resumeAnchorDomId({ section: anchor.section, entry_index: anchor.entry_index }),
  );
  if (!el) return false;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add(...SCROLL_HIGHLIGHT_CLASSES);
  window.setTimeout(() => {
    el.classList.remove(...SCROLL_HIGHLIGHT_CLASSES);
  }, 1800);
  return true;
}

/** Retry scroll until the editor mounts (e.g. after navigating from Export). */
export function scrollToResumeAnchorWithRetry(
  anchor: IssueAnchor,
  onDone?: (found: boolean) => void,
  attempts = 12,
  delayMs = 80,
): void {
  let tries = 0;
  const tick = () => {
    if (scrollToResumeAnchor(anchor)) {
      onDone?.(true);
      return;
    }
    tries += 1;
    if (tries >= attempts) {
      onDone?.(false);
      return;
    }
    window.setTimeout(tick, delayMs);
  };
  tick();
}
