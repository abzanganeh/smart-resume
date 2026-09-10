import type { TailoredExperience } from "@/lib/api";
import { matchExperienceCompany } from "@/lib/applyResumePatch";

/** Drop guard notes that no longer apply (e.g. dropped entry restored manually). */
export function filterStaleRewriteNotes(
  notes: string[],
  experience: TailoredExperience[],
): string[] {
  return notes.filter((note) => {
    const lower = note.toLowerCase();
    if (!lower.includes("dropped experience entry")) {
      return true;
    }
    const match = note.match(/Dropped experience entry for '([^']+)'/i);
    if (!match?.[1]) {
      return true;
    }
    const droppedCompany = match[1];
    const restored = experience.some((entry) =>
      matchExperienceCompany(entry.company, droppedCompany),
    );
    return !restored;
  });
}
