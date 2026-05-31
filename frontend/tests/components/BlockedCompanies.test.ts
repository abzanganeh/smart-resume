/**
 * Component tests for blocked company list add/remove logic.
 *
 * Run: pnpm exec tsx tests/components/BlockedCompanies.test.ts
 */
import { addBlockedCompany, removeBlockedCompany } from "../../lib/jobs"

function assert(condition: boolean, message: string) {
  if (!condition) throw new Error(`FAIL: ${message}`)
  console.log(`  PASS: ${message}`)
}

export function runTests() {
  console.log("\nBlockedCompanies component tests\n")

  let companies = ["Acme Corp"]

  companies = addBlockedCompany(companies, "Globex")
  assert(companies.length === 2, "add appends a new company")
  assert(companies.includes("Globex"), "add includes Globex")

  const beforeDup = companies.length
  companies = addBlockedCompany(companies, "  acme corp  ")
  assert(companies.length === beforeDup, "add ignores duplicate case-insensitive names")

  companies = addBlockedCompany(companies, "   ")
  assert(companies.length === beforeDup, "add ignores empty names")

  companies = removeBlockedCompany(companies, "Acme Corp")
  assert(!companies.includes("Acme Corp"), "remove deletes the selected company")
  assert(companies.includes("Globex"), "remove leaves other companies intact")

  companies = removeBlockedCompany(companies, "Missing Inc")
  assert(companies.length === 1, "remove on missing name is a no-op")

  console.log("\nAll tests passed.\n")
}

if (typeof process !== "undefined" && process.argv[1]?.endsWith("BlockedCompanies.test.ts")) {
  runTests()
}

export { runTests as default }
