"use client"

import { Briefcase, FileText, MessageSquare, Search, Sparkles, Target } from "lucide-react"
import { DashboardStepCard } from "@/components/dashboard/DashboardStepCard"
import {
  computeStepStates,
  type StepStackInputs,
} from "@/components/dashboard/stepStack.helpers"

export interface DashboardStepStackProps {
  hasMasterResume: boolean
  masterChunkCount: number
  masterUpdatedAt: string | null
  jobRolesReady: boolean
  jobRolesStale?: boolean
  preferredTitles: string[]
  tailoredResumeCount: number
  applicationCounts?: StepStackInputs["applicationCounts"]
  formatDate: (iso: string) => string
}

/**
 * Sequential dashboard progress stack.  Steps unlock in order and collapse
 * to slim two-button rows once complete so returning users see their next
 * action rather than the same expanded explainer every visit.
 *
 * All state transitions are computed by {@link computeStepStates} so unit
 * tests and the rendered UI cannot drift apart.
 */
export function DashboardStepStack({
  hasMasterResume,
  masterChunkCount,
  masterUpdatedAt,
  jobRolesReady,
  jobRolesStale = false,
  preferredTitles,
  tailoredResumeCount,
  applicationCounts = null,
  formatDate,
}: DashboardStepStackProps) {
  const states = computeStepStates({
    hasMasterResume,
    jobRolesReady,
    jobRolesStale,
    tailoredResumeCount,
    applicationCounts,
  })

  const titlesPreview =
    preferredTitles.length > 0
      ? preferredTitles.slice(0, 3).join(", ") +
        (preferredTitles.length > 3 ? ` +${preferredTitles.length - 3} more` : "")
      : ""

  const rolesReady = states.roles === "ready" || states.roles === "ready-stale"
  const rolesStale = states.roles === "ready-stale"
  const searchReady = states.search === "ready"
  const tailorReady = states.tailor === "ready"
  const applicationsReady = states.applications === "ready"

  return (
    <section
      className="space-y-3"
      aria-label="Your job search progress"
      data-testid="dashboard-step-stack"
    >
      {/* Step 1 — Master resume */}
      {states.master === "ready" ? (
        <DashboardStepCard
          step={1}
          icon={FileText}
          title={`Master resume ready · ${masterChunkCount} section${masterChunkCount === 1 ? "" : "s"}${masterUpdatedAt ? ` (${formatDate(masterUpdatedAt)})` : ""}`}
          description=""
          ready
          primaryHref="/session/new"
          primaryLabel="Tailor for a job"
          secondaryHref="/profile"
          secondaryLabel="View master"
          testId="dashboard-step-master"
        />
      ) : (
        <DashboardStepCard
          step={1}
          icon={FileText}
          title="Build your master resume"
          description="Your full career inventory. Include everything — we pick the strongest matches per job description. Upload, paste, or tell your story."
          ready={false}
          primaryHref="/profile?mode=story"
          primaryLabel="Start your story →"
          secondaryHref="/profile"
          secondaryLabel="Upload file"
          testId="dashboard-step-master"
        />
      )}

      {/* Step 2 — Job roles */}
      <DashboardStepCard
        step={2}
        icon={Target}
        title={
          rolesStale
            ? "Job roles need a refresh"
            : rolesReady
              ? `Job roles ready · ${titlesPreview}`
              : "Choose roles to search for"
        }
        description={
          rolesStale
            ? `Your master resume changed. Refresh suggestions to keep them accurate — free, no credit used. Current picks: ${titlesPreview || "none saved"}.`
            : rolesReady
              ? ""
              : hasMasterResume
                ? "We suggest ~10 titles from your resume — pick at least five to search our company job corpus."
                : "Complete your master resume first, then we will suggest job titles from your experience."
        }
        ready={rolesReady && !rolesStale}
        expandedWhenReady={rolesStale}
        locked={states.roles === "locked"}
        primaryHref={hasMasterResume ? "/jobs/setup?return=/dashboard" : undefined}
        primaryLabel={
          rolesStale
            ? "Refresh suggestions →"
            : rolesReady
              ? "Edit roles"
              : "Choose job roles →"
        }
        secondaryHref={rolesReady ? "/jobs" : undefined}
        secondaryLabel={rolesReady ? "Search jobs" : undefined}
        testId="dashboard-step-roles"
      />

      {/* Step 3 — Search jobs */}
      <DashboardStepCard
        step={3}
        icon={Search}
        title={searchReady ? "Search jobs ready" : "Search jobs"}
        description={
          searchReady
            ? ""
            : hasMasterResume
              ? "Unlocks once you choose your job roles above."
              : "Complete steps 1 and 2 to unlock job search."
        }
        ready={searchReady}
        locked={states.search === "locked"}
        primaryHref={searchReady ? "/jobs" : undefined}
        primaryLabel="Search jobs"
        secondaryHref={searchReady ? "/career-watch" : undefined}
        secondaryLabel={searchReady ? "Career Watch" : undefined}
        testId="dashboard-step-search"
      />

      {/* Step 4 — Tailor */}
      <DashboardStepCard
        step={4}
        icon={Sparkles}
        title={
          tailorReady
            ? `Tailored resumes · ${tailoredResumeCount} on file`
            : "Tailor for a job"
        }
        description={
          tailorReady
            ? ""
            : hasMasterResume
              ? "Paste a job description and TalioCV rewrites your resume against every ATS keyword — evidence-based, no fabricated metrics."
              : "Available after your master resume is ready."
        }
        ready={tailorReady}
        locked={states.tailor === "locked"}
        primaryHref={hasMasterResume ? "/session/new" : undefined}
        primaryLabel={tailorReady ? "New tailoring" : "Tailor now →"}
        secondaryHref={tailorReady ? "/dashboard#tailored-resumes" : undefined}
        secondaryLabel={tailorReady ? "View list" : undefined}
        testId="dashboard-step-tailor"
      />

      {/* Step 5 — Applications */}
      <DashboardStepCard
        step={5}
        icon={Briefcase}
        title={
          applicationsReady
            ? `Applications · ${applicationCounts?.active ?? 0} active · ${applicationCounts?.interviewing ?? 0} interviewing · ${applicationCounts?.offer ?? 0} offer${(applicationCounts?.offer ?? 0) === 1 ? "" : "s"}`
            : "Track applications"
        }
        description={
          applicationsReady
            ? ""
            : tailorReady
              ? "Log every tailored resume you send. Move applications through Applied → Interviewing → Offer to see your funnel over time."
              : "Available once you tailor your first resume."
        }
        ready={applicationsReady}
        locked={states.applications === "locked"}
        primaryHref={tailorReady ? "/tracker" : undefined}
        primaryLabel={applicationsReady ? "Open tracker" : "Add application →"}
        secondaryHref={applicationsReady ? "/fit" : undefined}
        secondaryLabel={applicationsReady ? "Score a fit" : undefined}
        testId="dashboard-step-applications"
      />

      {/* Step 6 — Prepare for interview (locked placeholder) */}
      <DashboardStepCard
        step={6}
        icon={MessageSquare}
        title="Prepare for interviews"
        description="Coming soon: coached interview prep with Flint, our real-time interview co-pilot. Unlocks after your first interview stage."
        ready={false}
        locked
        comingSoon
        testId="dashboard-step-prepare"
      />
    </section>
  )
}
