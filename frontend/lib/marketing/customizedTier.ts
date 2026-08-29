import { PRODUCT_NAME, SALES_INQUIRY_EMAIL } from "@/lib/brand";

/** Public landing card — not a Stripe plan code. */
export const CUSTOMIZED_TIER_DISPLAY_NAME = "Customized" as const;

export const CUSTOMIZED_TIER_PRICE_LABEL = "Custom quote" as const;

export const CUSTOMIZED_TIER_SUBLINE =
  "Tell us what you need — we'll send a quote." as const;

export const CUSTOMIZED_TIER_CTA = "Contact us" as const;

export const CUSTOMIZED_TIER_HIGHLIGHTS = [
  "Volume & limits tailored to your team",
  "Model routing configured per deal",
  "Onboarding support for org rollouts",
  "Not sold through self-serve checkout",
] as const;

/** mailto link for the landing CTA — no backend / no new route. */
export function customizedTierContactHref(): string {
  const subject = encodeURIComponent(`${PRODUCT_NAME} Customized plan inquiry`);
  return `mailto:${SALES_INQUIRY_EMAIL}?subject=${subject}`;
}
