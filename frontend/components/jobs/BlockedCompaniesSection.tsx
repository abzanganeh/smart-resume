"use client"

import { useState } from "react"
import { Building2, Plus, X } from "lucide-react"
import { addBlockedCompany, removeBlockedCompany } from "@/lib/jobs"

interface Props {
  companies: string[]
  onChange: (companies: string[]) => void
  saving?: boolean
}

export function BlockedCompaniesSection({ companies, onChange, saving }: Props) {
  const [input, setInput] = useState("")

  const addCompany = () => {
    const next = addBlockedCompany(companies, input)
    if (next !== companies) {
      onChange(next)
    }
    setInput("")
  }

  const removeCompany = (name: string) => {
    onChange(removeBlockedCompany(companies, name))
  }

  return (
    <section data-testid="blocked-companies-section">
      <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-1">Blocked companies</h2>
      <p className="text-sm text-slate-600 dark:text-slate-400 mb-4">
        Jobs from these companies are hidden from your search results.
      </p>

      <div className="flex gap-2 mb-4">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault()
              addCompany()
            }
          }}
          placeholder="Company name"
          data-testid="blocked-company-input"
          className="flex-1 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-800 dark:text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-amber-400"
        />
        <button
          type="button"
          onClick={addCompany}
          disabled={saving || !input.trim()}
          data-testid="blocked-company-add"
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 text-sm font-medium hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-40"
        >
          <Plus className="w-4 h-4" />
          Add
        </button>
      </div>

      {companies.length === 0 ? (
        <p className="text-sm text-slate-600 dark:text-slate-400">No blocked companies yet.</p>
      ) : (
        <ul className="space-y-2" data-testid="blocked-company-list">
          {companies.map((company) => (
            <li
              key={company}
              className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900"
            >
              <span className="inline-flex items-center gap-2 text-sm text-slate-800 dark:text-slate-200">
                <Building2 className="w-4 h-4 text-slate-600 dark:text-slate-400 shrink-0" />
                {company}
              </span>
              <button
                type="button"
                onClick={() => removeCompany(company)}
                disabled={saving}
                aria-label={`Remove ${company}`}
                data-testid={`blocked-company-remove-${company}`}
                className="p-1.5 rounded-lg text-slate-600 dark:text-slate-400 hover:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/40 disabled:opacity-40"
              >
                <X className="w-4 h-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
