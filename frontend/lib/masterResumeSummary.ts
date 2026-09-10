/** Human-readable master resume stats for dashboard copy (not RAG chunk_count). */

function asList(value: unknown): unknown[] {
  if (Array.isArray(value)) return value
  if (value && typeof value === "object") return [value]
  if (typeof value === "string" && value.trim()) return [value]
  return []
}

/**
 * Summarize parsed_sections as roles / schools / projects the user recognizes.
 * Returns null when structured parse is empty (caller can fall back to "indexed").
 */
export function summarizeMasterResume(
  parsedSections: Record<string, unknown> | null | undefined,
): string | null {
  if (!parsedSections || typeof parsedSections !== "object") return null

  const parts: string[] = []

  const roles = asList(parsedSections.experience).length
  if (roles > 0) parts.push(`${roles} role${roles === 1 ? "" : "s"}`)

  const schools = asList(parsedSections.education).length
  if (schools > 0) parts.push(`${schools} school${schools === 1 ? "" : "s"}`)

  const projects = asList(parsedSections.project).length
  if (projects > 0) parts.push(`${projects} project${projects === 1 ? "" : "s"}`)

  const certs = asList(parsedSections.cert).length
  if (certs > 0) parts.push(`${certs} cert${certs === 1 ? "" : "s"}`)

  if (parts.length > 0) return parts.slice(0, 3).join(" · ")

  let sections = 0
  if (typeof parsedSections.summary === "string" && parsedSections.summary.trim()) {
    sections += 1
  }
  if (asList(parsedSections.skills).length > 0) sections += 1
  for (const key of [
    "publication",
    "award",
    "patent",
    "language",
    "volunteer",
    "other",
  ] as const) {
    if (asList(parsedSections[key]).length > 0) sections += 1
  }

  if (sections > 0) return `${sections} section${sections === 1 ? "" : "s"}`
  return null
}
