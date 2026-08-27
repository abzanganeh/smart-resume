import type { Metadata } from "next"
import { LegalPageShell } from "@/components/legal/LegalPageShell"

export const metadata: Metadata = {
  title: "Sub-processors — TalioCV",
  description:
    "List of sub-processors used by TalioCV.  Updated with 30-day notice as required by our Privacy Policy.",
}

const LAST_UPDATED = "2026-08-27"

type Subprocessor = {
  name: string
  purpose: string
  region: string
  privacyUrl: string
}

const SUBPROCESSORS: Subprocessor[] = [
  {
    name: "Amazon Web Services (AWS)",
    purpose:
      "Compute (ECS / Lambda), database (RDS PostgreSQL with pgvector), object storage (S3 — exports + attachments), event scheduling (EventBridge), queues (SQS).",
    region: "us-east-1",
    privacyUrl: "https://aws.amazon.com/privacy/",
  },
  {
    name: "Stripe",
    purpose:
      "Subscription billing, payment processing, refunds, webhook delivery.  Card data is tokenised by Stripe and never reaches our servers.",
    region: "Global (US headquartered)",
    privacyUrl: "https://stripe.com/privacy",
  },
  {
    name: "Resend",
    purpose:
      "Transactional email delivery (verification, password reset, payment-failure notifications, refund decisions, DPO contact replies).",
    region: "Global (US headquartered)",
    privacyUrl: "https://resend.com/legal/privacy-policy",
  },
  {
    name: "Twilio",
    purpose:
      "Optional SMS delivery for interview / application reminders.  Only triggered when the user opts in to SMS notifications.",
    region: "Global (US headquartered)",
    privacyUrl: "https://www.twilio.com/legal/privacy",
  },
  {
    name: "Hirebase",
    purpose:
      "Real-time job-search semantic provider used by /jobs.  Only the search query and minimal context (location, job preferences) are forwarded.",
    region: "Global",
    privacyUrl: "https://hirebase.io/privacy",
  },
  {
    name: "Apify",
    purpose:
      "Background scraper actor used to refresh the local job-cache nightly so Hirebase outages degrade gracefully.",
    region: "Global (Czech Republic / EU)",
    privacyUrl: "https://apify.com/privacy-policy",
  },
  {
    name: "Sentry",
    purpose:
      "Error monitoring &amp; performance tracing.  PII bodies are scrubbed before transmission; only stack traces, request paths, and structured tags are sent.",
    region: "Global (US / EU regions available)",
    privacyUrl: "https://sentry.io/privacy/",
  },
  {
    name: "Google (Gemini)",
    purpose:
      "LLM provider for platform-managed AI on every plan.  Processes résumé and job-description text for keyword extraction, gap analysis, rewriting, and quality checks.  Plans differ by how much you can run, not by which model runs it.",
    region: "Global (US headquartered)",
    privacyUrl: "https://policies.google.com/privacy",
  },
  {
    name: "OpenAI",
    purpose:
      "Platform-owned embedding model (used for master-résumé chunk retrieval and fit scoring) and Whisper speech-to-text for voice input on paid plans.  We do not accept customer-supplied API keys.",
    region: "Global (US headquartered)",
    privacyUrl: "https://openai.com/policies/privacy-policy",
  },
]

export default function SubProcessorsPage() {
  return (
    <LegalPageShell title="Sub-processors" lastUpdated={LAST_UPDATED}>
      <p>
        TalioCV engages the following sub-processors to operate the
        Service.  This list is updated with at least <strong>30 days&apos;
        notice</strong> before any material change, in line with §19.9 of our
        system design and Section 4 of the{" "}
        <a href="/legal/privacy">Privacy Policy</a>.
      </p>
      <p>
        To receive automated change notices, subscribe via the{" "}
        <a href="/legal/contact">DPO contact form</a> and request the
        sub-processor mailing list.
      </p>

      <h2>Current sub-processors</h2>
      <ul>
        {SUBPROCESSORS.map((p) => (
          <li key={p.name}>
            <strong>{p.name}</strong> ({p.region}) — {p.purpose}{" "}
            <a href={p.privacyUrl} target="_blank" rel="noreferrer noopener">
              Privacy &amp; DPA
            </a>
          </li>
        ))}
      </ul>

      <h2>How we choose sub-processors</h2>
      <p>
        Every sub-processor is required to (a) sign a Data Processing
        Addendum or equivalent, (b) provide adequate technical and
        organisational safeguards, and (c) host data in jurisdictions
        compatible with our cross-border transfer mechanism (Standard
        Contractual Clauses where applicable).
      </p>

      <h2>Object to a sub-processor</h2>
      <p>
        If you object to a new sub-processor within the 30-day notice
        window, contact{" "}
        <a href="mailto:privacy@zanganehai.com">privacy@zanganehai.com</a>.
        We will discuss reasonable alternatives or, where impossible,
        provide an exit path with a refund of pre-paid unused fees.
      </p>
    </LegalPageShell>
  )
}
