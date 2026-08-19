import { stripJdBoilerplate } from "@/lib/jdBoilerplate";

/** Apply JD cleanup before submit or length checks. */
export function normalizeJdText(raw: string): string {
  return stripJdBoilerplate(raw.trim());
}
