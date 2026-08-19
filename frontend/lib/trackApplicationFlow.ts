/**
 * Client helper for "Track application" from jobs or tailor session.
 * Handles duplicate_application with a synchronous confirm callback so callers
 * can use window.confirm or a modal without duplicating the 409 retry logic.
 */

import {
  createApplication,
  TrackerApiError,
  type ApplicationSummary,
} from "@/lib/tracker"

export type TrackApplicationBody = Parameters<typeof createApplication>[1]

export async function trackApplicationWithDuplicatePrompt(
  token: string,
  body: TrackApplicationBody,
  confirmDuplicate: (err: TrackerApiError) => boolean,
): Promise<ApplicationSummary> {
  try {
    return await createApplication(token, body)
  } catch (err) {
    if (err instanceof TrackerApiError && err.code === "duplicate_application") {
      if (confirmDuplicate(err)) {
        return createApplication(token, { ...body, confirm_add_duplicate: true })
      }
    }
    throw err
  }
}

export function formatTrackerLimitError(err: TrackerApiError): string {
  if (err.code !== "tracker_limit_reached") return err.message
  return `${err.message} Archive an application on the Applications page or upgrade your plan.`
}
