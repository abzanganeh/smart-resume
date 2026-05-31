import {
  isSubscriptionActive,
  yearlyDiscountedAmount,
  yearlySavingsAmount,
} from "@/lib/billing"

function assert(condition: boolean, message: string) {
  if (!condition) throw new Error(`FAIL: ${message}`)
  console.log(`  PASS: ${message}`)
}

function runTests() {
  console.log("\nBilling logic tests\n")

  assert(
    yearlyDiscountedAmount(1999) === 19190,
    "monthly 1999 cents -> yearly discounted amount is 19190",
  )
  assert(
    yearlySavingsAmount(1999) === 4798,
    "yearly savings derived from monthly amount are correct",
  )

  assert(isSubscriptionActive("active"), "active subscription is treated as active")
  assert(isSubscriptionActive("trialing"), "trialing subscription is treated as active")
  assert(
    isSubscriptionActive("cancel_at_period_end"),
    "cancel_at_period_end subscription remains active",
  )
  assert(!isSubscriptionActive("cancelled"), "cancelled subscription is inactive")
  assert(!isSubscriptionActive("expired"), "expired subscription is inactive")

  console.log("\nAll billing logic tests passed.\n")
}

if (typeof process !== "undefined" && process.argv[1]?.endsWith("BillingLogic.test.ts")) {
  runTests()
}

export { runTests }
