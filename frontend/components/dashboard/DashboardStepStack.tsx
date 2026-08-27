"use client"

import Link from "next/link"
import {
  Briefcase,
  ClipboardPaste,
  FileText,
  Plug,
  Search,
  Sparkles,
  Target,
} from "lucide-react"
import { COMPANY_LINE, COMPANY_URL, PRODUCT_NAME } from "@/lib/brand"
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
  hasJd: boolean
  preferredTitles: string[]
  tailoredResumeCount: number
  applicationCounts?: StepStackInputs["applicationCounts"]
  formatDate: (iso: string) => string
}

const FLINT_PRODUCT_NAME = "Flint"

/**
 * Sequential dashboard progress stack.  Steps unlock in order and collapse
 * to slim two-button rows once complete so returning users see their next
 * action rather than the same expanded explainer every visit.
 *
 * Locks are recommendations only — routes stay open; locked cards may expose
 * a skip CTA ("Use this feature now") for users who want to jump ahead.
 */
export function DashboardStepStack({
  hasMasterResume,
  masterChunkCount,
  masterUpdatedAt,
  jobRolesReady,
  jobRolesStale = false,
  hasJd,
  preferredTitles,
  tailoredResumeCount,
  applicationCounts = null,
  formatDate,
}: DashboardStepStackProps) {
  const states = computeStepStates({
    hasMasterResume,
    jobRolesReady,
    jobRolesStale,
    hasJd,
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
  const rolesEffectivelyReady = hasMasterResume && jobRolesReady
  const searchReady = states.search === "ready"
  const captureReady = states.capture === "ready"
  const tailorReady = states.tailor === "ready"
  const applyReady = states.apply === "ready"
  const applicationsReady = states.applications === "ready"
  const hasTailored = tailoredResumeCount > 0

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
                ? "We suggest ~10 titles from your resume — pick the ones you want (up to 12), or add your own."
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
        skipHref={states.search === "locked" && hasMasterResume ? "/jobs" : undefined}
        skipLabel={
          states.search === "locked" && hasMasterResume ? "Use this feature now →" : undefined
        }
        testId="dashboard-step-search"
      />

      {/* Step 4 — Capture JD (extension) */}
      <DashboardStepCard
        step={4}
        icon={Plug}
        title={captureReady ? "Job posting captured" : "Capture a job posting"}
        description={
          captureReady
            ? ""
            : rolesEffectivelyReady
              ? `Use the ${PRODUCT_NAME} browser extension on Greenhouse, Lever, Ashby, and similar sites — or save a posting from in-app search.`
              : "Complete your master resume and job roles first."
        }
        ready={captureReady}
        locked={states.capture === "locked"}
        primaryHref={rolesEffectivelyReady ? COMPANY_URL : undefined}
        primaryLabel="How the extension works"
        secondaryHref={rolesEffectivelyReady ? "/jobs" : undefined}
        secondaryLabel={rolesEffectivelyReady ? "Search & save jobs" : undefined}
        skipHref={
          states.capture === "locked" && hasMasterResume
            ? "/jobs/setup?return=/dashboard"
            : undefined
        }
        skipLabel={
          states.capture === "locked" && hasMasterResume
            ? "Choose job roles first →"
            : undefined
        }
        testId="dashboard-step-capture"
      />

      {/* Step 5 — Tailor */}
      <DashboardStepCard
        step={5}
        icon={Sparkles}
        title={
          tailorReady
            ? `Tailored resumes · ${tailoredResumeCount} on file`
            : "Tailor your resume"
        }
        description={
          tailorReady
            ? ""
            : rolesEffectivelyReady && !hasJd
              ? `Recommended after you capture or save a job description — paste in ${PRODUCT_NAME} or send one from the extension.`
              : hasMasterResume
                ? `Paste a job description or use an extension handoff — ${PRODUCT_NAME} rewrites your resume against every ATS keyword with evidence from your master resume.`
                : "Available after your master resume is ready."
        }
        ready={tailorReady}
        locked={states.tailor === "locked"}
        primaryHref={hasJd || hasMasterResume ? "/session/new" : undefined}
        primaryLabel={tailorReady ? "New tailoring" : "Tailor now →"}
        secondaryHref={tailorReady ? "/dashboard#tailored-resumes" : undefined}
        secondaryLabel={tailorReady ? "View list" : undefined}
        skipHref={
          states.tailor === "locked" && rolesEffectivelyReady
            ? "/session/new"
            : undefined
        }
        skipLabel={
          states.tailor === "locked" && rolesEffectivelyReady
            ? "Use this feature now →"
            : undefined
        }
        testId="dashboard-step-tailor"
      />

      {/* Step 6 — Apply with autofill */}
      <DashboardStepCard
        step={6}
        icon={ClipboardPaste}
        title={applyReady ? "Applied with autofill" : "Apply with autofill"}
        description={
          applyReady
            ? ""
            : hasTailored
              ? `Return to the employer site with the ${PRODUCT_NAME} extension — autofill application forms from your tailored resume.`
              : "Recommended after you tailor a resume for the posting."
        }
        ready={applyReady}
        locked={states.apply === "locked"}
        primaryHref={hasTailored ? COMPANY_URL : undefined}
        primaryLabel="Extension autofill guide"
        secondaryHref={hasTailored ? "/tracker" : undefined}
        secondaryLabel={hasTailored ? "Track application" : undefined}
        skipHref={
          states.apply === "locked" && (hasJd || rolesEffectivelyReady)
            ? "/session/new"
            : undefined
        }
        skipLabel={
          states.apply === "locked" && hasJd
            ? "Tailor a resume first →"
            : states.apply === "locked" && rolesEffectivelyReady
              ? "Use this feature now →"
              : undefined
        }
        testId="dashboard-step-apply"
      />

      {/* Step 7 — Track applications */}
      <DashboardStepCard
        step={7}
        icon={Briefcase}
        title={
          applicationsReady
            ? `Applications · ${applicationCounts?.active ?? 0} active · ${applicationCounts?.interviewing ?? 0} interviewing · ${applicationCounts?.offer ?? 0} offer${(applicationCounts?.offer ?? 0) === 1 ? "" : "s"}`
            : "Track applications"
        }
        description={
          applicationsReady
            ? ""
            : rolesEffectivelyReady
              ? "Log every application you send. Move rows through Applied → Interviewing → Offer to see your funnel over time."
              : "Unlocks once you choose your job roles above."
        }
        ready={applicationsReady}
        locked={states.applications === "locked"}
        primaryHref={rolesEffectivelyReady ? "/tracker" : undefined}
        primaryLabel={applicationsReady ? "Open tracker" : "Add application →"}
        secondaryHref={applicationsReady ? "/fit" : undefined}
        secondaryLabel={applicationsReady ? "Score a fit" : undefined}
        skipHref={
          states.applications === "locked" && hasMasterResume ? "/tracker" : undefined
        }
        skipLabel={
          states.applications === "locked" && hasMasterResume
            ? "Use this feature now →"
            : undefined
        }
        testId="dashboard-step-applications"
      />

      {/* Flint desktop — separate product, not part of the numbered ladder */}
      <div
        className="rounded-2xl border border-dashed border-slate-300 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-900/30 px-6 py-5"
        data-testid="dashboard-flint-coming-soon"
      >
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">
          Coming soon
        </p>
        <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">
          <span className="font-semibold text-slate-900 dark:text-white">{FLINT_PRODUCT_NAME}</span>
          {" — live interview co-pilot (separate desktop app {COMPANY_LINE}). "}
          Not included in your {PRODUCT_NAME} subscription.{" "}
          <Link
            href={COMPANY_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-amber-800 dark:text-amber-300 hover:underline"
          >
            Learn more →
          </Link>
        </p>
      </div>
    </section>
  )
}
