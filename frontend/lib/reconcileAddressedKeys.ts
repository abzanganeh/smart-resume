import type { BlockingIssue, QAOutput } from "@/lib/api";
import { issueKey } from "@/lib/issueAnchors";

/** After re-score: keep addressed keys only for issues no longer blocking. */
export function reconcileAddressedKeys(
  prev: ReadonlySet<string>,
  qaOut: QAOutput,
): Set<string> {
  const stillBlocking = new Set(
    (qaOut.blocking_issues ?? []).map((issue) => issueKey(issue)),
  );
  const next = new Set<string>();
  for (const key of prev) {
    if (!stillBlocking.has(key)) next.add(key);
  }
  return next;
}
