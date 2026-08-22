/** Map backend / NextAuth error codes to user-facing copy. */
export function friendlyAuthError(code: string): string {
  const ssoMatch = /^email_registered_with_sso:(.+)$/.exec(code)
  if (ssoMatch) {
    const provider = ssoMatch[1]
    const label =
      provider === "google"
        ? "Google"
        : provider === "github"
          ? "GitHub"
          : provider === "microsoft"
            ? "Microsoft"
            : provider === "email"
              ? "email and password"
              : provider
    return `This email is already registered with ${label}. Sign in that way instead of SSO.`
  }

  const map: Record<string, string> = {
    invalid_credentials: "Invalid email or password.",
    sso_sign_in_required:
      "This account uses Google sign-in, not a password. Use Continue with Google on the Sign in tab.",
    email_registered_with_sso:
      "This email is already registered with Google. Switch to Sign in — email/password is not set up for this account.",
    email_already_registered:
      "An account with this email already exists. Switch to Sign in instead.",
    account_locked:
      "Account temporarily locked after too many failed attempts. Try again in 15 minutes.",
    account_suspended: "This account has been suspended. Contact support.",
    turnstile_failed: "Human verification failed. Please complete the check and try again.",
    disposable_email_not_allowed:
      "Disposable email addresses cannot be used to sign up. Use a personal or work email you can receive mail at.",
    reset_token_expired:
      "This reset link has expired. Request a new one to change your password.",
    reset_token_invalid:
      "This reset link is invalid. Request a new one to change your password.",
    user_not_found: "This reset link is no longer valid. Request a new one.",
    "not found":
      "The API did not recognize this request. Point NEXT_PUBLIC_API_URL at the FastAPI backend, not the Playwright mock.",
    "Failed to fetch": "Could not reach the API. Is the backend running?",
    tfa_invalid: "Invalid TOTP code or recovery code.",
    challenge_token_invalid: "Your 2FA session has expired. Please log in again.",
    OAuthBackendSyncPending:
      "Sign-in succeeded but the app could not reach the API. Sign out and try again.",
    missing_api_token:
      "Your session is missing an API token. Sign out and sign in again.",
    OAuthSignin: "Could not initiate SSO. Please try again.",
    Configuration:
      "Sign-in could not finish — usually the browser host does not match the OAuth callback (try the same URL you opened, e.g. localhost vs LAN IP). If this persists, confirm GOOGLE_CLIENT_SECRET in frontend/.env.local and restart npm run dev.",
    OAuthCallback: "SSO callback failed. Please try again.",
    Default: "Something went wrong. Please try again.",
  }
  return map[code] ?? map["Default"]
}
