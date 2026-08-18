/** User-facing promo redeem error copy — mirrors backend codes. */

const PROMO_ERROR_MESSAGES: Record<string, string> = {
  promo_code_invalid: "That code is not valid.",
  promo_code_expired: "That code has expired.",
  promo_code_exhausted: "That code has already been used up.",
  promo_code_inactive: "That code is not valid.",
  promo_misconfigured: "This code could not be applied. Please contact support.",
}

export function promoRedeemErrorMessage(code: string | undefined): string {
  if (code && PROMO_ERROR_MESSAGES[code]) {
    return PROMO_ERROR_MESSAGES[code]
  }
  return "That code is not valid."
}

export function promoRedeemSuccessMessage(creditsAdded: number): string {
  const label = creditsAdded === 1 ? "credit" : "credits"
  return `Code applied — ${creditsAdded} ${label} added.`
}
