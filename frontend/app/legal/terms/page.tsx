import type { Metadata } from "next"
import { LegalPageShell } from "@/components/legal/LegalPageShell"

export const metadata: Metadata = {
  title: "Terms of Service — TalioCV",
  description:
    "Terms of Service for TalioCV.  Acceptance, license, prohibited uses, payment terms, termination, and governing law.",
}

const LAST_UPDATED = "2026-05-31"

export default function TermsPage() {
  return (
    <LegalPageShell title="Terms of Service" lastUpdated={LAST_UPDATED}>
      <p>
        These Terms of Service (&quot;Terms&quot;) govern your access to and use
        of TalioCV (the &quot;Service&quot;), provided by Alireza
        Barzin Zanganeh (&quot;TalioCV&quot;, &quot;we&quot;, &quot;us&quot;).  By
        creating an account or using the Service you agree to these Terms.  If
        you do not agree, do not use the Service.
      </p>

      <h2>1. Acceptance &amp; Account</h2>
      <p>
        You must be at least 16 years old to register.  You agree to provide
        accurate registration information and to keep your credentials
        confidential.  You are responsible for any activity under your account.
      </p>

      <h2>2. License Grant</h2>
      <p>
        TalioCV grants you a limited, non-exclusive, non-transferable,
        revocable license to access and use the Service for your personal or
        internal business resume / cover letter / job-search workflow,
        consistent with these Terms and the{" "}
        <a href="https://mariadb.com/bsl11/">Business Source License 1.1</a>{" "}
        under which the source code is published.  See the project{" "}
        <code>LICENSE</code> file for parameters and the Change Date that
        converts the source license to Apache 2.0.
      </p>

      <h2>3. Prohibited Uses</h2>
      <p>You agree not to:</p>
      <ul>
        <li>
          Use the Service to generate misleading résumés that misrepresent
          your background, qualifications, or work history.
        </li>
        <li>
          Reverse-engineer, scrape, or attempt to extract platform data outside
          the documented APIs.
        </li>
        <li>
          Resell or commercialize Service output beyond the license grant
          without a separate commercial agreement (see <code>COMMERCIAL.md</code>).
        </li>
        <li>
          Upload malicious content, content that infringes a third party&apos;s
          rights, or content that violates applicable law.
        </li>
        <li>
          Probe, scan, disrupt, or test the vulnerability of the Service or any
          related infrastructure without written permission.
        </li>
      </ul>

      <h2>4. Subscriptions, Credits &amp; Payment</h2>
      <p>
        Paid plans are billed by Stripe under the cycle and price disclosed at
        checkout.  Refunds are governed by our policy:
      </p>
      <ul>
        <li>
          Self-service full refund within 24 hours of the first paid charge.
        </li>
        <li>
          Self-service full refund within 7 days when no usage occurred during
          the period.
        </li>
        <li>
          Beyond those windows, refund requests are reviewed by our team and
          subject to super-admin approval.
        </li>
      </ul>
      <p>
        Cancellation, pause, downgrade, and upgrade behaviour is documented in
        our pricing page and matches the contract referenced in our system
        design (§19.8).  Pause is available on Monthly + Yearly plans only,
        for up to 90 days.
      </p>

      <h2>5. Intellectual Property</h2>
      <p>
        You retain ownership of content you upload (master résumé, attachments,
        notes).  TalioCV retains ownership of the Service, the user
        interface, the platform code, and the model orchestration layer.
        Output generated for your account is yours to use; the underlying
        prompt &amp; retrieval pipelines remain ours.
      </p>

      <h2>6. Termination</h2>
      <p>
        You may terminate your account at any time via Settings → Close
        Account.  We may suspend or terminate accounts that breach these
        Terms, abuse the Service, or fail payment obligations.  On
        termination we honour the data retention &amp; deletion windows in
        the Privacy Policy.
      </p>

      <h2>7. Disclaimers</h2>
      <p>
        The Service is provided &quot;as is&quot;.  AI-generated résumé and
        cover-letter drafts may contain inaccuracies; you are responsible for
        reviewing every word before sending it to a recruiter or applicant
        tracking system.
      </p>

      <h2>8. Limitation of Liability</h2>
      <p>
        To the maximum extent permitted by law, TalioCV&apos;s aggregate
        liability for any claim arising from these Terms is limited to the
        fees you paid us in the 12 months preceding the claim.
      </p>

      <h2>9. Governing Law &amp; Disputes</h2>
      <p>
        These Terms are governed by the laws of the State of California, USA,
        without regard to conflict-of-laws principles.  Disputes that cannot
        be resolved informally will be brought in the state or federal courts
        located in San Francisco County, California.
      </p>

      <h2>10. Changes</h2>
      <p>
        We may update these Terms from time to time.  Material changes will be
        announced in-product and via email at least 30 days before they take
        effect, in line with §19.9 of our system design.
      </p>

      <h2>11. Contact</h2>
      <p>
        Questions about these Terms?  Reach our Data Protection Officer at{" "}
        <a href="mailto:privacy@zanganehai.com">privacy@zanganehai.com</a> or
        via the{" "}
        <a href="/legal/contact">DPO contact form</a>.
      </p>
    </LegalPageShell>
  )
}
