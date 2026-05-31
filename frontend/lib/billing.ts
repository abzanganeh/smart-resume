import type { SubscriptionStatus } from "./api"

const INACTIVE_SUBSCRIPTION_STATUSES: SubscriptionStatus[] = ["cancelled", "expired"]

export function isSubscriptionActive(status: SubscriptionStatus): boolean {
  return !INACTIVE_SUBSCRIPTION_STATUSES.includes(status)
}

export function yearlyDiscountedAmount(monthlyAmountCents: number): number {
  return Math.round(monthlyAmountCents * 12 * 0.8)
}

export function yearlySavingsAmount(monthlyAmountCents: number): number {
  const yearly = yearlyDiscountedAmount(monthlyAmountCents)
  return monthlyAmountCents * 12 - yearly
}
