import type { ResumePatch } from "@/lib/api";
import { matchProjectName } from "@/lib/applyResumePatch";

export type SuggestionStatus = "pending" | "accepted" | "rejected";

export interface ResumeSuggestion {
  id: string;
  patch: ResumePatch;
  status: SuggestionStatus;
}

export function makeSuggestions(patches: ResumePatch[]): ResumeSuggestion[] {
  return patches.map((patch) => ({
    id: crypto.randomUUID(),
    patch,
    status: "pending",
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
): ResumeSuggestion[] {
  const incoming = makeSuggestions(patches);
  const targetedProjects = [
    ...new Set(
      patches
        .map((p) => patchTargetsProjectName(p))
        .filter((name): name is string => !!name),
    ),
  ];

  const kept =
    targetedProjects.length === 0
      ? prev
      : prev.filter((s) => {
          if (s.status !== "pending") return true;
          const target = patchTargetsProjectName(s.patch);
          if (!target) return true;
          return !targetedProjects.some((name) => matchProjectName(target, name));
        });

  return [...kept, ...incoming];
}
