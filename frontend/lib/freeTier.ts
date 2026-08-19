const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Fallback when the public free-tier endpoint is unreachable. */
export const FREE_TIER_STARTING_CREDITS = 3;

export const VOICE_AVAILABILITY_COPY =
  "Live transcription is free in Chrome and Edge; Firefox and Safari use Whisper (2 credits per story).";

export const FREE_TIER_CREDIT_ACTIONS = [
  { action: "Resume tailor (full pipeline)", cost: "1 credit" },
  { action: "Cover letter generation", cost: "1 credit" },
  { action: "Coached story interview", cost: "1 credit" },
  { action: "Story resume regenerate", cost: "1 credit" },
  { action: "Story resume re-save", cost: "1 credit" },
  { action: "Whisper story transcription", cost: "2 credits" },
  { action: "ATS score recalculation", cost: "1 credit" },
] as const;

export async function fetchFreeTierStartingCredits(): Promise<number> {
  try {
    const res = await fetch(`${BASE}/api/billing/free-tier`, {
      next: { revalidate: 60 },
    });
    if (!res.ok) {
      return FREE_TIER_STARTING_CREDITS;
    }
    const data = (await res.json()) as { starting_credits?: unknown };
    return typeof data.starting_credits === "number"
      ? data.starting_credits
      : FREE_TIER_STARTING_CREDITS;
  } catch {
    return FREE_TIER_STARTING_CREDITS;
  }
}

export function formatSignupCreditsCopy(count: number): string {
  const label = count === 1 ? "credit" : "credits";
  return `${count} ${label} on signup`;
}
