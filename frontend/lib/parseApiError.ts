/** Shared FastAPI `detail` parsing for client fetch helpers. */

export const SESSION_REPLACED_CODE = "session_replaced";
export const SESSION_REVOKED_EVENT = "app:session-revoked";

export function parseApiErrorDetail(
  detail: unknown,
  status: number,
): { message: string; code?: string } {
  if (typeof detail === "string") {
    return { message: detail };
  }
  if (detail && typeof detail === "object") {
    const d = detail as Record<string, unknown>;
    const code = typeof d.code === "string" ? d.code : undefined;
    const candidate = d.message ?? d.error;
    if (typeof candidate === "string") {
      return { message: candidate, code };
    }
    if (code === "insufficient_credits") {
      const action = typeof d.action === "string" ? d.action : undefined;
      if (action === "ats_recalc") {
        return {
          code,
          message:
            "You're out of credits. ATS score recalculation costs 1 credit.",
        };
      }
      return {
        code,
        message: "You're out of credits. Subscribe from Billing to keep going.",
      };
    }
    if (code === "subscription_required") {
      return { code, message: "This feature requires an active subscription." };
    }
    if (code === SESSION_REPLACED_CODE) {
      return {
        code,
        message:
          "You signed in somewhere else. Sign in again to continue.",
      };
    }
    if (typeof code === "string") {
      return { message: code, code };
    }
    return { message: JSON.stringify(detail) };
  }
  return { message: `HTTP ${status}` };
}

/** Dispatch when the backend rejects a superseded access token. */
export function notifySessionRevoked(code?: string): void {
  if (typeof window === "undefined" || code !== SESSION_REPLACED_CODE) return;
  window.dispatchEvent(
    new CustomEvent(SESSION_REVOKED_EVENT, { detail: code }),
  );
}

export function sessionRevokedAuthUrl(): string {
  const dest =
    typeof window !== "undefined"
      ? `${window.location.pathname}${window.location.search}`
      : "/";
  return `/auth?error=${SESSION_REPLACED_CODE}&callbackUrl=${encodeURIComponent(dest)}`;
}
