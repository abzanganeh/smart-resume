import { ApiError } from "./api";

// Platform AI runs on our keys, so a provider billing rejection is ours to
// fix, not something the user can top up. Point at support, not a provider.
const LLM_HELP_URL = "/legal/contact";

/** Turn API and unknown errors into user-facing copy with optional action hints. */
export function userFacingError(error: unknown): {
  message: string;
  code?: string;
  helpUrl?: string;
} {
  if (error instanceof ApiError) {
    if (error.code === "resume_empty" || error.code === "resume_too_short") {
      return { message: error.message, code: error.code };
    }
    if (error.code === "insufficient_credits") {
      return {
        message: error.message,
        code: error.code,
      };
    }
    if (error.status === 402) {
      return {
        message:
          error.message ||
          "The AI service rejected the request on our side. Retry in a moment — if it keeps failing, let us know.",
        code: error.code ?? "payment_required",
        helpUrl: LLM_HELP_URL,
      };
    }
    if (error.status === 401 || error.code === "unauthorized") {
      return {
        message:
          error.code === "session_replaced"
            ? "You signed in somewhere else. Sign in again to continue."
            : "Your session expired. Sign in again and retry.",
        code: error.code ?? "unauthorized",
      };
    }
    if (error.status === 429 || error.code === "rate_limited") {
      return {
        message: "Too many requests — wait a moment and try again.",
        code: error.code ?? "rate_limited",
      };
    }
    if (error.message && !error.message.startsWith("HTTP ")) {
      return { message: error.message, code: error.code };
    }
  }

  if (error instanceof Error) {
    const lower = error.message.toLowerCase();
    if (lower.includes("402") || lower.includes("not enough credits")) {
      return {
        message:
          "The AI service is out of credit on our side. Retry in a moment — if it keeps failing, let us know.",
        code: "llm_insufficient_credits",
        helpUrl: LLM_HELP_URL,
      };
    }
    if (lower.includes("401") || lower.includes("unauthorized")) {
      return {
        message: "Authentication failed — sign in again and retry.",
        code: "llm_auth",
      };
    }
    if (lower.includes("429") || lower.includes("rate limit")) {
      return {
        message: "The AI provider is rate-limiting requests. Wait a moment and retry.",
        code: "llm_rate_limit",
      };
    }
    return { message: error.message };
  }

  return { message: "Something went wrong. Please try again." };
}
