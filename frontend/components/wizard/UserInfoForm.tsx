"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Pencil } from "lucide-react";
import { type ParsedResume, type UserInfoPayload } from "@/lib/api";

interface Props {
  onSubmit: (info: UserInfoPayload) => void;
  loading?: boolean;
  /** Data parsed from the uploaded resume — used to pre-fill fields. */
  parsedResume?: ParsedResume | null;
  /** Raw JD text — used to detect AI/ML roles and show the transition toggle. */
  jdText?: string;
}

const CAREER_STAGES: { value: UserInfoPayload["career_stage"]; label: string; hint: string }[] = [
  { value: "student", label: "Student / New Grad", hint: "0–1 year · 1-page resume" },
  { value: "entry",   label: "Entry Level",         hint: "1–3 years · 1-page resume" },
  { value: "mid",     label: "Mid Level",            hint: "3–7 years · 1–2 pages" },
  { value: "senior",  label: "Senior",               hint: "7–12 years · 2-page resume" },
  { value: "staff",   label: "Staff / Lead / Principal", hint: "10+ years · 2-page resume" },
  { value: "executive", label: "Director / VP / Executive", hint: "15+ years · 2-page resume" },
];

const AI_ML_SIGNALS = [
  "machine learning", "ml engineer", "deep learning", "neural network",
  "llm", "large language model", "generative ai", "mlops", "pytorch",
  "tensorflow", "data scientist", "computer vision", "nlp",
  "artificial intelligence", " ai ", "reinforcement learning",
];

function isAiMlJob(jdText: string): boolean {
  const lower = jdText.toLowerCase();
  return AI_ML_SIGNALS.some((s) => lower.includes(s));
}

/** Badge shown next to a field that was pre-filled from the resume. */
function FilledBadge() {
  return (
    <span className="inline-flex items-center gap-1 ml-2 text-emerald-700 dark:text-emerald-400 text-[10px] font-medium">
      <CheckCircle2 className="h-3 w-3" />
      from resume
    </span>
  );
}

export function UserInfoForm({ onSubmit, loading, parsedResume, jdText = "" }: Props) {
  const contact = parsedResume?.contact;
  const resumeCerts = parsedResume?.certifications ?? [];

  const [form, setForm] = useState<UserInfoPayload>({
    name: contact?.name ?? "",
    email: contact?.email ?? "",
    phone: contact?.phone ?? "",
    linkedin: contact?.linkedin ?? "",
    github: contact?.github ?? "",
    location: contact?.location ?? "",
    website: contact?.website ?? "",
    career_stage: "mid",
    target_role: "",
    certifications: resumeCerts,
    is_career_transition: false,
  });
  const [stageConfirmed, setStageConfirmed] = useState(false);

  const [certsInput, setCertsInput] = useState(resumeCerts.join(", "));

  // Re-sync if parsedResume arrives after first render
  useEffect(() => {
    if (!parsedResume) return;
    const c = parsedResume.contact;
    setForm((f) => ({
      ...f,
      name:     f.name     || c.name     || "",
      email:    f.email    || c.email    || "",
      phone:    f.phone    || c.phone    || "",
      linkedin: f.linkedin || c.linkedin || "",
      github:   f.github   || c.github   || "",
      location: f.location || c.location || "",
      website:  f.website  || c.website  || "",
      certifications: f.certifications.length ? f.certifications : parsedResume.certifications,
    }));
    if (!certsInput) setCertsInput(parsedResume.certifications.join(", "));
  }, [parsedResume]);

  // Extension JD captures often lead with the role title on line 1.
  useEffect(() => {
    if (!jdText.trim()) return;
    const firstLine = jdText.trim().split("\n")[0]?.trim() ?? "";
    const looksLikeTitle =
      firstLine.length > 0 &&
      firstLine.length <= 80 &&
      !firstLine.includes("|") &&
      !/^salary:/i.test(firstLine);
    if (!looksLikeTitle) return;
    setForm((f) => (f.target_role ? f : { ...f, target_role: firstLine }));
  }, [jdText]);

  const set = <K extends keyof UserInfoPayload>(key: K, value: UserInfoPayload[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const certs = certsInput.split(",").map((s) => s.trim()).filter(Boolean);
    onSubmit({ ...form, certifications: certs });
  };

  const inputCls =
    "w-full bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-slate-800 dark:text-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 placeholder-slate-600";
  const labelCls = "flex items-center text-slate-600 dark:text-slate-400 text-xs mb-1 font-medium";

  const showTransitionToggle = isAiMlJob(jdText);

  // Track which fields came from the resume so we can badge them
  const preFilled = {
    name:     !!contact?.name,
    email:    !!contact?.email,
    phone:    !!contact?.phone,
    linkedin: !!contact?.linkedin,
    github:   !!contact?.github,
    certs:    resumeCerts.length > 0,
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5">

      {/* ── Contact info ──────────────────────────────────────────────── */}
      <div className="rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-100/40 dark:bg-slate-800/40 p-4 space-y-4">
        <p className="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">
          Contact — verify or correct what we found
        </p>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={labelCls}>
              Full Name
              {preFilled.name && <FilledBadge />}
            </label>
            <input
              value={form.name ?? ""}
              onChange={(e) => set("name", e.target.value)}
              placeholder="Jane Doe"
              className={inputCls}
            />
          </div>
          <div>
            <label className={labelCls}>
              Email
              {preFilled.email && <FilledBadge />}
            </label>
            <input
              type="email"
              value={form.email ?? ""}
              onChange={(e) => set("email", e.target.value)}
              placeholder="jane.doe@example.com"
              className={inputCls}
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={labelCls}>
              Phone
              {preFilled.phone && <FilledBadge />}
            </label>
            <input
              value={form.phone ?? ""}
              onChange={(e) => set("phone", e.target.value)}
              placeholder="+1 555 000 0000"
              className={inputCls}
            />
          </div>
          <div>
            <label className={labelCls}>
              LinkedIn
              {preFilled.linkedin && <FilledBadge />}
            </label>
            <input
              value={form.linkedin ?? ""}
              onChange={(e) => set("linkedin", e.target.value)}
              placeholder="linkedin.com/in/…"
              className={inputCls}
            />
          </div>
        </div>

        <div>
          <label className={labelCls}>
            GitHub
            {preFilled.github && <FilledBadge />}
          </label>
          <input
            value={form.github ?? ""}
            onChange={(e) => set("github", e.target.value)}
            placeholder="github.com/…"
            className={inputCls}
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={labelCls}>Location</label>
            <input
              value={form.location ?? ""}
              onChange={(e) => set("location", e.target.value)}
              placeholder="City, State"
              className={inputCls}
            />
          </div>
          <div>
            <label className={labelCls}>Website / Portfolio</label>
            <input
              value={form.website ?? ""}
              onChange={(e) => set("website", e.target.value)}
              placeholder="yourportfolio.com"
              className={inputCls}
            />
          </div>
        </div>
      </div>

      {/* ── Role & Stage ──────────────────────────────────────────────── */}
      <div className="rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-100/40 dark:bg-slate-800/40 p-4 space-y-4">
        <p className="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">
          Role & Experience Level
        </p>

        <div>
          <label className={labelCls}>Target Role *</label>
          <input
            required
            value={form.target_role}
            onChange={(e) => set("target_role", e.target.value)}
            placeholder="e.g. Registered Nurse, Product Manager, Software Engineer, Data Analyst…"
            className={inputCls}
          />
          <p className="text-slate-600 dark:text-slate-400 text-[11px] mt-1">
            Any role, any industry — be as specific as the job posting.
          </p>
        </div>

        <div>
          <label className={labelCls}>Career Stage *</label>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {CAREER_STAGES.map(({ value, label, hint }) => (
              <button
                key={value}
                type="button"
                onClick={() => {
                  set("career_stage", value);
                  setStageConfirmed(true);
                }}
                className={`text-left px-3 py-2.5 rounded-lg border text-sm transition-all ${
                  form.career_stage === value && stageConfirmed
                    ? "border-amber-400 bg-amber-500/10 dark:bg-amber-400/10 text-amber-700 dark:text-amber-300"
                    : "border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:border-slate-500"
                }`}
              >
                <span className="font-medium">{label}</span>
                <span className="block text-[11px] mt-0.5 text-slate-600 dark:text-slate-400">{hint}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Certifications ────────────────────────────────────────────── */}
      <div>
        <label className={labelCls}>
          Certifications
          {preFilled.certs && <FilledBadge />}
        </label>
        <input
          value={certsInput}
          onChange={(e) => setCertsInput(e.target.value)}
          placeholder="e.g. AWS Solutions Architect, PMP, Google Analytics — comma separated"
          className={inputCls}
        />
        <p className="text-slate-600 dark:text-slate-400 text-[11px] mt-1">Leave blank if none.</p>
      </div>

      {/* ── Career transition (only for AI/ML JDs) ────────────────────── */}
      {showTransitionToggle && (
        <div className="rounded-xl border border-violet-500/30 bg-violet-500/5 p-4">
          <div className="flex items-start gap-3">
            <input
              type="checkbox"
              id="transition"
              checked={form.is_career_transition}
              onChange={(e) => set("is_career_transition", e.target.checked)}
              className="mt-0.5 w-4 h-4 rounded accent-violet-400 shrink-0"
            />
            <label htmlFor="transition" className="text-slate-700 dark:text-slate-300 text-sm cursor-pointer leading-relaxed">
              I'm transitioning into AI/ML from another field
              <span className="block text-slate-600 dark:text-slate-400 text-xs mt-0.5">
                The rewrite will highlight transferable skills and frame your background
                as complementary experience for this AI role.
              </span>
            </label>
          </div>
        </div>
      )}

      {/* ── Editable note ─────────────────────────────────────────────── */}
      <p className="flex items-center gap-1.5 text-slate-600 dark:text-slate-400 text-xs">
        <Pencil className="h-3 w-3" />
        All fields pre-filled from your resume are editable — correct anything that looks wrong.
      </p>

      <button
        type="submit"
        disabled={loading || !form.target_role.trim() || !stageConfirmed}
        className="w-full py-2.5 bg-amber-400 text-slate-900 font-semibold rounded-lg hover:bg-amber-300 disabled:opacity-40 transition-colors"
      >
        {loading ? "Saving…" : "Continue →"}
      </button>
    </form>
  );
}
