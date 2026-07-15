/** Persist checkup inputs across auth redirect into a tailoring session. */

const HANDOFF_KEY = "sr_checkup_handoff";

export interface CheckupHandoff {
  resumeText: string;
  jdText: string;
  jobTitle: string;
}

export function saveCheckupHandoff(handoff: CheckupHandoff): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(HANDOFF_KEY, JSON.stringify(handoff));
}

export function getCheckupHandoff(): CheckupHandoff | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(HANDOFF_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CheckupHandoff;
    if (!parsed?.jdText?.trim()) return null;
    return {
      resumeText: parsed.resumeText ?? "",
      jdText: parsed.jdText,
      jobTitle: parsed.jobTitle ?? "",
    };
  } catch {
    return null;
  }
}

export function clearCheckupHandoff(): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(HANDOFF_KEY);
}
