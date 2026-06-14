import type { ResumePatch } from "@/lib/api";

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
