import type { Metadata } from "next"
import { LegalPageShell } from "@/components/legal/LegalPageShell"

export const metadata: Metadata = {
  title: "Privacy Policy — TalioCV",
  description:
    "Privacy Policy for TalioCV.  GDPR lawful bases, data categories, retention periods, and your rights.",
}

const LAST_UPDATED = "2026-08-21"

export default function PrivacyPage() {
  return (
    <LegalPageShell title="Privacy Policy" lastUpdated={LAST_UPDATED}>
      <p>
        This Privacy Policy explains how TalioCV (&quot;we&quot;,
        &quot;us&quot;) collects, uses, shares, and protects your information.
        TalioCV is operated by Alireza Barzin Zanganeh.  Our Data Protection
        Officer (DPO) can be reached at{" "}
        <a href="mailto:privacy@zanganehai.com">privacy@zanganehai.com</a>.
      </p>

      <h2>1. Lawful Bases (GDPR Art. 6)</h2>
      <ul>
        <li>
          <strong>Performance of contract</strong> — running your subscription,
          building tailored résumés / cover letters, and answering support
          tickets.
        </li>
        <li>
          <strong>Consent</strong> — marketing emails, optional analytics, and
          opt-in features.  You can withdraw consent at any time without
          affecting prior processing.
        </li>
        <li>
          <strong>Legitimate interest</strong> — security audit logs, fraud
          prevention, and platform abuse mitigation.  These are minimised and
          balanced against your rights.
        </li>
        <li>
          <strong>Legal obligation</strong> — financial / tax record-keeping
          for paid transactions.
        </li>
      </ul>

      <h2>2. Categories of Data We Process</h2>
      <ul>
        <li>
          <strong>Account &amp; identity</strong>: email, display name,
          authentication provider (email / Google / GitHub / Microsoft /
          LinkedIn), TOTP secret (encrypted), recovery code hashes.
        </li>
        <li>
          <strong>Profile &amp; résumé content</strong>: master résumé,
          chunks, generated tailored versions, cover letters, fit scores,
          embeddings.
        </li>
        <li>
          <strong>Job-search activity</strong>: saved searches, cached job
          rows, application tracker entries.
        </li>
        <li>
          <strong>Security &amp; fraud prevention</strong>: signup IP address,
          hashed device/browser fingerprint (never raw fingerprint inputs),
          Turnstile signals, and auth audit metadata. Processed under
          legitimate interest (GDPR Art. 6(1)(f)) to prevent free-tier abuse.
          Under EU ePrivacy rules, reading device characteristics for this
          purpose is disclosed here rather than via a separate cookie banner.
        </li>
        <li>
          <strong>Billing</strong>: Stripe customer / subscription IDs,
          payment-failure timestamps, refund records.  Card data never
          touches our servers.
        </li>
        <li>
          <strong>Usage telemetry</strong>: minimised structured logs (no
          plaintext secrets, no full PII bodies) for security and reliability.
        </li>
      </ul>

      <h2>3. Retention</h2>
      <p>The following retention windows apply:</p>
      <ul>
        <li>Account &amp; profile data — for the lifetime of your account.</li>
        <li>
          Generated résumé / cover-letter outputs — kept readable for 90 days
          after subscription ends; archived 1 year cold; then purged.
        </li>
        <li>
          <code>AdminAuditLog</code> — 7 years (financial / compliance).
        </li>
        <li><code>AuthAuditLog</code> — 1 year.</li>
        <li>
          Signup IP and hashed device fingerprint — retained while the account
          is active and for up to 90 days after closure, then deleted with other
          account metadata (aligned with auth audit retention).
        </li>
        <li>
          <code>Notification</code> rows — 90 days hot, then archived 1 year.
        </li>
        <li>
          Application logs (structlog) — 30 days hot in CloudWatch, 1 year
          cold in S3, then deleted.
        </li>
        <li>
          Account closure — soft-delete with a 30-day grace; backups purged
          within 60 days of grace expiry. Résumé chunks and vector embeddings
          are removed when closure executes.
        </li>
      </ul>

      <h2>4. Sub-processors</h2>
      <p>
        We share data with the sub-processors listed at{" "}
        <a href="/legal/sub-processors">/legal/sub-processors</a>.  Material
        changes are announced with at least 30 days&apos; notice in line with
        the §19.9 contract.
      </p>

      <h2>5. Your Rights</h2>
      <ul>
        <li>
          <strong>Access</strong> — export your data at any time via{" "}
          <code>POST /api/account/export</code>; the resulting ZIP includes
          machine-readable JSON + CSV.
        </li>
        <li>
          <strong>Erasure</strong> — close your account via{" "}
          <code>POST /api/account/close</code>; soft-deleted with a 30-day
          grace, backups purged within 60 days of grace expiry. Master-résumé
          chunks, user-corpus fragments, and their pgvector embeddings are
          hard-deleted when closure executes (GDPR Art. 17).
        </li>
        <li>
          <strong>Rectification</strong> — update profile data via the
          settings UI or the <code>/api/profile/resume</code> endpoint.
        </li>
        <li>
          <strong>Data portability</strong> — the export ZIP is
          machine-readable.
        </li>
        <li>
          <strong>Object / restrict processing</strong> — pause your
          subscription (§19.8) or opt out of marketing.
        </li>
        <li>
          <strong>Lodge a complaint</strong> — you may complain to your
          national data protection authority.
        </li>
      </ul>

      <h2>6. Children</h2>
      <p>
        TalioCV is not directed at users under 16.  Registration requires
        a self-attestation checkbox.  If you believe a minor has registered,
        contact us and we will close the account.
      </p>

      <h2>7. International Transfers</h2>
      <p>
        Our infrastructure runs on AWS in the United States.  Where data
        leaves the EEA / UK we rely on Standard Contractual Clauses with our
        sub-processors.  See the sub-processor page for region details.
      </p>

      <h2>8. Security</h2>
      <ul>
        <li>
          Secrets at rest encrypted with AES-256-GCM. We do not accept or store
          customer-supplied LLM API keys.
        </li>
        <li>TOTP secrets encrypted; recovery codes stored hashed only.</li>
        <li>Strict CORS allowlist, signed Stripe webhooks, audited admin actions.</li>
        <li>
          15-minute access tokens, 7-day rotating refresh tokens with reuse
          detection.
        </li>
      </ul>

      <h2>9. CCPA / California Residents</h2>
      <p>
        See <a href="/legal/ccpa">/legal/ccpa</a> for our &quot;Do Not Sell My
        Personal Information&quot; statement: <strong>we do not sell user
        data</strong>.
      </p>

      <h2>10. Contact &amp; SLA</h2>
      <p>
        Reach our DPO at{" "}
        <a href="mailto:privacy@zanganehai.com">privacy@zanganehai.com</a>{" "}
        or via the <a href="/legal/contact">contact form</a>.  We respond
        to formal data-subject requests within 30 days.
      </p>
    </LegalPageShell>
  )
}
