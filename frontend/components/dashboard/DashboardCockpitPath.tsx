"use client"

import { FileText, Search, Target } from "lucide-react"
import { CockpitStepCard } from "@/components/dashboard/CockpitStepCard"

interface DashboardCockpitPathProps {
  hasMasterResume: boolean
  masterChunkCount: number
  masterUpdatedAt: string | null
  jobRolesReady: boolean
  jobRolesStale?: boolean
  preferredTitles: string[]
  formatDate: (iso: string) => string
}

export function DashboardCockpitPath({
  hasMasterResume,
  masterChunkCount,
  masterUpdatedAt,
  jobRolesReady,
  jobRolesStale = false,
  preferredTitles,
  formatDate,
}: DashboardCockpitPathProps) {
  const titlesPreview =
    preferredTitles.length > 0
      ? preferredTitles.slice(0, 3).join(", ") +
        (preferredTitles.length > 3 ? ` +${preferredTitles.length - 3} more` : "")
      : ""

  return (
    <section className="space-y-3" aria-label="Your job search path">
      {!hasMasterResume ? (
        <CockpitStepCard
          step={1}
          icon={FileText}
          title="Build your master resume"
          description="Upload, paste, or tell your story — voice with live transcription is free in Chrome and Edge."
          ready={false}
          primaryHref="/profile?mode=story"
          primaryLabel="Start your story →"
          secondaryHref="/profile"
          secondaryLabel="Upload file"
        />
      ) : (
        <CockpitStepCard
          step={1}
          icon={FileText}
          title="Master resume ready"
          description={`${masterChunkCount} indexed section${masterChunkCount === 1 ? "" : "s"}${masterUpdatedAt ? ` · last updated ${formatDate(masterUpdatedAt)}` : ""}. This is the foundation for tailoring and job matching.`}
          ready
          primaryHref="/session/new"
          primaryLabel="Tailor for a job →"
          secondaryHref="/profile"
          secondaryLabel="View master resume"
        />
      )}

      <CockpitStepCard
        step={2}
        icon={Target}
        title={
          jobRolesReady && jobRolesStale
            ? "Job roles need a refresh"
            : jobRolesReady
              ? "Job roles ready"
              : "Choose roles to search for"
        }
        description={
          jobRolesReady && jobRolesStale
            ? `Your master resume changed. Refresh suggestions to keep them accurate — free, no credit used. Current picks: ${titlesPreview || "none saved"}.`
            : jobRolesReady
              ? `Searching for: ${titlesPreview}. Edit anytime if your targets change.`
              : hasMasterResume
                ? "We suggest ~10 titles from your resume — pick at least five to search our company job corpus."
                : "Complete your master resume first, then we will suggest job titles from your experience."
        }
        ready={jobRolesReady && !jobRolesStale}
        locked={!hasMasterResume}
        primaryHref={hasMasterResume ? "/jobs/setup?return=/dashboard" : undefined}
        primaryLabel={
          jobRolesReady && jobRolesStale
            ? "Refresh suggestions →"
            : jobRolesReady
              ? "Edit job roles →"
              : "Choose job roles →"
        }
        secondaryHref={jobRolesReady ? "/jobs" : undefined}
        secondaryLabel={jobRolesReady ? "Preview titles" : undefined}
      />

      <CockpitStepCard
        step={3}
        icon={Search}
        title="Search jobs"
        description={
          jobRolesReady
            ? "Find openings from 500+ tech employers. Click a role on the Jobs page or search manually — included on the free plan."
            : hasMasterResume
              ? "Available after you choose your job roles (step 2)."
              : "Complete steps 1 and 2 to unlock job search."
        }
        ready={jobRolesReady}
        locked={!jobRolesReady}
        primaryHref={jobRolesReady ? "/jobs" : undefined}
        primaryLabel="Search jobs →"
        secondaryHref={jobRolesReady ? "/tracker" : undefined}
        secondaryLabel={jobRolesReady ? "Application tracker" : undefined}
      />
    </section>
  )
}
