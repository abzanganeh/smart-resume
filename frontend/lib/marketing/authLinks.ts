/** Post-auth destination for landing-page upgrade CTAs. */
export const BILLING_CALLBACK_PATH = "/billing";

/**
 * Auth URL that returns visitors to `/billing` after SSO or email sign-in.
 *
 * Register mode pre-selects the signup tab; login opens the sign-in tab.
 * Both preserve `callbackUrl` through OAuth round-trips via `resolveAuthReturnUrl`.
 */
export function authUrlForBilling(mode: "register" | "login" = "register"): string {
  const params = new URLSearchParams();
  if (mode === "register") {
    params.set("mode", "register");
  }
  params.set("callbackUrl", BILLING_CALLBACK_PATH);
  return `/auth?${params.toString()}`;
}
