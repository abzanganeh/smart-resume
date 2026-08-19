import type { Metadata } from "next"
import { LegalPageShell } from "@/components/legal/LegalPageShell"

export const metadata: Metadata = {
  title: "Do Not Sell My Personal Information — TalioCV",
  description:
    "California Consumer Privacy Act (CCPA) statement.  TalioCV does not sell user personal information.",
}

const LAST_UPDATED = "2026-05-31"

export default function CcpaPage() {
  return (
    <LegalPageShell
      title="Do Not Sell My Personal Information"
      lastUpdated={LAST_UPDATED}
    >
      <p>
        This page satisfies the &quot;Do Not Sell My Personal Information&quot;
        notice required of California businesses under the California Consumer
        Privacy Act (CCPA), as amended by the California Privacy Rights Act
        (CPRA).
      </p>

      <h2>Our position</h2>
      <p>
        <strong>
          TalioCV does not sell or &quot;share&quot; (as those
          terms are defined under the CCPA / CPRA) the personal information
          of any user — California resident or otherwise.
        </strong>{" "}
        We do not exchange your résumé, profile, generated content, search
        history, or any other data for monetary or other valuable
        consideration with third parties.
      </p>
      <p>
        Because we do not sell or share, no opt-out action is required to
        prevent a sale.  You are already opted out by default, and we operate
        a Global Privacy Control (GPC) honouring posture for any future
        feature that might involve advertising vendors.
      </p>

      <h2>Sub-processors are not sales</h2>
      <p>
        We do disclose limited personal information to the sub-processors
        listed at <a href="/legal/sub-processors">/legal/sub-processors</a>{" "}
        strictly to operate the Service (hosting, billing, email delivery,
        error monitoring, model inference).  These transfers are governed by
        Data Processing Addenda; sub-processors are contractually prohibited
        from using the data for their own purposes and from selling or
        sharing it.
      </p>

      <h2>Categories of personal information we collect</h2>
      <ul>
        <li>Identifiers (email, account ID, optional display name).</li>
        <li>
          Commercial information (subscription status, payment-failure
          history, refund records).
        </li>
        <li>
          Internet / network activity (request paths, IPs in security audit
          logs, minimised for non-PII bodies).
        </li>
        <li>
          Professional / employment information you upload (résumé, work
          history, cover letters, fit scores).
        </li>
      </ul>
      <p>
        See the <a href="/legal/privacy">Privacy Policy</a> for full
        retention windows and the lawful bases under which each category is
        processed.
      </p>

      <h2>Your CCPA rights</h2>
      <ul>
        <li>
          <strong>Right to know</strong> — request a copy of the personal
          information we hold via <code>POST /api/account/export</code>.
        </li>
        <li>
          <strong>Right to delete</strong> — close your account via{" "}
          <code>POST /api/account/close</code>.  Soft-deleted with a 30-day
          grace; backups purged within 60 days of grace expiry.
        </li>
        <li>
          <strong>Right to correct</strong> — update your profile / résumé
          fields in Settings.
        </li>
        <li>
          <strong>Right to non-discrimination</strong> — exercising any of
          the above rights does not affect the price or quality of the
          Service.
        </li>
        <li>
          <strong>Right to opt out of sale / sharing</strong> — already opted
          out for every user; no action required.
        </li>
      </ul>

      <h2>Submitting a request</h2>
      <p>
        Use the in-product Settings → Privacy controls, or contact our DPO at{" "}
        <a href="mailto:privacy@zanganehai.com">privacy@zanganehai.com</a> /
        the <a href="/legal/contact">contact form</a>.  We verify identity by
        confirming the request from the email associated with your account
        and respond within 45 days.
      </p>
    </LegalPageShell>
  )
}
