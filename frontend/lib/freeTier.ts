const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Fallback when the public free-tier endpoint is unreachable.
 *
 * Must track the backend registration grant (`tier_limits.py` free
 * `resumes_per_period`) — the landing hero renders this number, so a stale
 * value advertises an offer we do not honour.
 */
export const FREE_TIER_STARTING_CREDITS = 3;

export const VOICE_AVAILABILITY_COPY =
  "Live transcription is free in Chrome and Edge. Whisper on Firefox and Safari requires a paid plan.";

/** Credit-priced actions on the free tier — keep in sync with backend quota rules. */
export const FREE_TIER_CREDIT_ACTIONS = [
  { action: "Tailored rewrite", cost: "1 credit" },
  { action: "QA & export (ATS score)", cost: "1 credit" },
  { action: "Cover letter generation", cost: "1 credit" },
  { action: "Coached story interview", cost: "1 credit / session" },
  { action: "Story resume regenerate", cost: "First free; then 1" },
  { action: "Story resume save", cost: "First free; then 1" },
] as const;

/** Monthly allowances that do not debit the credit balance (free tier). */
export const FREE_TIER_NON_CREDIT_LIMITS_COPY =
  "Resume checkup: 3 per month (no credits). JD keyword analysis is free.";

export async function fetchFreeTierStartingCredits(): Promise<number> {
  try {
    const res = await fetch(`${BASE}/api/billing/free-tier`, {
      next: { revalidate: 60 },
      // Awaited during SSR of the public landing page — a stalled backend
      // must not hang the request.
      signal: AbortSignal.timeout(2_000),
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
