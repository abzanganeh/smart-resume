"use client";

import { useState } from "react";
import { type UserInfoPayload } from "@/lib/api";

interface Props {
  onSubmit: (info: UserInfoPayload) => void;
  loading?: boolean;
}

export function UserInfoForm({ onSubmit, loading }: Props) {
  const [form, setForm] = useState<UserInfoPayload>({
    name: "",
    email: "",
    phone: "",
    linkedin: "",
    github: "",
    career_stage: "senior",
    target_role_type: "ml_engineer",
    certifications: [],
    is_transitioning_to_ml: false,
  });
  const [certsInput, setCertsInput] = useState("");

  const set = (key: keyof UserInfoPayload, value: unknown) =>
    setForm((f) => ({ ...f, [key]: value }));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const certs = certsInput.split(",").map((s) => s.trim()).filter(Boolean);
    onSubmit({ ...form, certifications: certs });
  };

  const inputCls = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 placeholder-slate-600";
  const labelCls = "block text-slate-400 text-xs mb-1 font-medium";
  const selectCls = `${inputCls} cursor-pointer`;

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className={labelCls}>Full Name *</label>
          <input required value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Jane Doe" className={inputCls} />
        </div>
        <div>
          <label className={labelCls}>Professional Email *</label>
          <input required type="email" value={form.email} onChange={(e) => set("email", e.target.value)} placeholder="jane.doe@example.com" className={inputCls} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className={labelCls}>Phone</label>
          <input value={form.phone} onChange={(e) => set("phone", e.target.value)} placeholder="+1 555 000 0000" className={inputCls} />
        </div>
        <div>
          <label className={labelCls}>LinkedIn URL</label>
          <input value={form.linkedin} onChange={(e) => set("linkedin", e.target.value)} placeholder="https://linkedin.com/in/..." className={inputCls} />
        </div>
      </div>

      <div>
        <label className={labelCls}>GitHub URL</label>
        <input value={form.github} onChange={(e) => set("github", e.target.value)} placeholder="https://github.com/..." className={inputCls} />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className={labelCls}>Career Stage *</label>
          <select value={form.career_stage} onChange={(e) => set("career_stage", e.target.value)} className={selectCls}>
            <option value="early_mid">Early / Mid career (1 page max)</option>
            <option value="senior">Senior (2 pages max)</option>
          </select>
        </div>
        <div>
          <label className={labelCls}>Target Role *</label>
          <select value={form.target_role_type} onChange={(e) => set("target_role_type", e.target.value)} className={selectCls}>
            <option value="ml_engineer">ML Engineer</option>
            <option value="swe">Software Engineer</option>
            <option value="data_scientist">Data Scientist</option>
            <option value="other">Other</option>
          </select>
        </div>
      </div>

      <div>
        <label className={labelCls}>Certifications (comma-separated)</label>
        <input value={certsInput} onChange={(e) => setCertsInput(e.target.value)} placeholder="Coursera ML Specialization, AWS Solutions Architect" className={inputCls} />
      </div>

      <div className="flex items-center gap-3">
        <input
          type="checkbox"
          id="transitioning"
          checked={form.is_transitioning_to_ml}
          onChange={(e) => set("is_transitioning_to_ml", e.target.checked)}
          className="w-4 h-4 rounded accent-amber-400"
        />
        <label htmlFor="transitioning" className="text-slate-300 text-sm cursor-pointer">
          I'm transitioning to ML/AI from another field
        </label>
      </div>

      <button
        type="submit"
        disabled={loading}
        className="w-full py-2.5 bg-amber-400 text-slate-900 font-semibold rounded-lg hover:bg-amber-300 disabled:opacity-40 transition-colors"
      >
        {loading ? "Saving…" : "Continue →"}
      </button>
    </form>
  );
}
