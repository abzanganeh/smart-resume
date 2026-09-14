import type { ResumePatch } from "@/lib/api";
import { matchProjectName } from "@/lib/applyResumePatch";

export type SuggestionStatus = "pending" | "accepted" | "rejected";

export interface ResumeSuggestion {
  id: string;
  patch: ResumePatch;
  status: SuggestionStatus;
  sourceIssueKey?: string;
}

export function makeSuggestions(
  patches: ResumePatch[],
  sourceIssueKeys?: Array<string | undefined>,
): ResumeSuggestion[] {
  return patches.map((patch, index) => ({
    id: crypto.randomUUID(),
    patch,
    status: "pending",
    sourceIssueKey: sourceIssueKeys?.[index],
  }));
}

function patchTargetsProjectName(patch: ResumePatch): string | null {
  if (patch.section !== "projects") return null;
  if (patch.project_name?.trim()) return patch.project_name.trim();
  if (patch.new_project?.name?.trim()) return patch.new_project.name.trim();
  return null;
}

/** Drop stale pending suggestions superseded by a new chat batch for the same project. */
export function mergeSuggestionBatch(
  prev: ResumeSuggestion[],
  patches: ResumePatch[],
  sourceIssueKeys?: Array<string | undefined>,
): ResumeSuggestion[] {
  const incoming = makeSuggestions(patches, sourceIssueKeys);
  const incomingAnchorKeys = new Set(
    incoming.map((s) => s.sourceIssueKey).filter((key): key is string => !!key),
  );
  const targetedProjects = [
    ...new Set(
      patches
        .map((p) => patchTargetsProjectName(p))
        .filter((name): name is string => !!name),
    ),
  ];

  const kept = prev.filter((s) => {
    if (s.status !== "pending") return true;
    if (s.sourceIssueKey && incomingAnchorKeys.has(s.sourceIssueKey)) return false;
    if (targetedProjects.length === 0) return true;
    const target = patchTargetsProjectName(s.patch);
    if (!target) return true;
    return !targetedProjects.some((name) => matchProjectName(target, name));
  });

  return [...kept, ...incoming];
}
