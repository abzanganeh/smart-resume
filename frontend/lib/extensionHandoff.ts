/** Persist extension JD handoff across auth / onboarding redirects. */

const HANDOFF_KEY = "sr_extension_jd_handoff"

export interface ExtensionHandoff {
  jd_id: string
  source: string
  step: string
  jd_review?: boolean
}

export function saveExtensionHandoff(handoff: ExtensionHandoff): void {
  if (typeof window === "undefined") return
  sessionStorage.setItem(HANDOFF_KEY, JSON.stringify(handoff))
}

export function getExtensionHandoff(): ExtensionHandoff | null {
  if (typeof window === "undefined") return null
  try {
    const raw = sessionStorage.getItem(HANDOFF_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as ExtensionHandoff
    if (!parsed?.jd_id) return null
    return {
      jd_id: parsed.jd_id,
      source: parsed.source ?? "extension",
      step: parsed.step ?? "jd",
      jd_review: parsed.jd_review,
    }
  } catch {
    return null
  }
}

export function clearExtensionHandoff(): void {
  if (typeof window === "undefined") return
  sessionStorage.removeItem(HANDOFF_KEY)
}

/** Parse jd_id/source/step from a path+query string or full URL. */
export function parseExtensionHandoffFromUrl(urlOrPath: string): ExtensionHandoff | null {
  try {
    const base =
      typeof window !== "undefined" ? window.location.origin : "http://localhost"
    const parsed = urlOrPath.startsWith("http")
      ? new URL(urlOrPath)
      : new URL(urlOrPath, base)
    const jdId = parsed.searchParams.get("jd_id")
    if (!jdId) return null
    return {
      jd_id: jdId,
      source: parsed.searchParams.get("source") ?? "extension",
      step: parsed.searchParams.get("step") ?? "jd",
      jd_review: parsed.searchParams.get("jd_review") === "1",
    }
  } catch {
    return null
  }
}

export function captureExtensionHandoffFromUrl(urlOrPath: string): ExtensionHandoff | null {
  const handoff = parseExtensionHandoffFromUrl(urlOrPath)
  if (handoff) saveExtensionHandoff(handoff)
  return handoff
}

export function captureExtensionHandoffFromParams(
  params: Pick<URLSearchParams, "get">,
): ExtensionHandoff | null {
  const jdId = params.get("jd_id")
  if (!jdId) return null
  const handoff: ExtensionHandoff = {
    jd_id: jdId,
    source: params.get("source") ?? "extension",
    step: params.get("step") ?? "jd",
    jd_review: params.get("jd_review") === "1",
  }
  saveExtensionHandoff(handoff)
  return handoff
}

export function buildSessionNewUrl(handoff: ExtensionHandoff): string {
  const params = new URLSearchParams({
    step: handoff.step,
    jd_id: handoff.jd_id,
    source: handoff.source,
  })
  if (handoff.jd_review) params.set("jd_review", "1")
  return `/session/new?${params.toString()}`
}
