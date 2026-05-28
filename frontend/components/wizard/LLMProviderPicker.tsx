"use client";

import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { getLLMProviders, type LLMProvider } from "@/lib/api";

interface Props {
  value: string;
  model: string;
  onChange: (provider: string, model: string) => void;
}

export function LLMProviderPicker({ value, model, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [providers, setProviders] = useState<LLMProvider[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    getLLMProviders()
      .then((r) => {
        setProviders(r.providers);
        setLoadError(null);
        // If current provider isn't in list (no key), default to first available
        if (r.providers.length > 0 && !r.providers.find((p) => p.id === value)) {
          const first = r.providers[0];
          onChange(first.id, first.model);
        }
      })
      .catch(() => setLoadError("Could not load LLM providers. Is the backend running?"));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const selected = providers.find((p) => p.id === value);
  const modelOptions = selected?.models ?? [];
  const selectedModelMeta = modelOptions.find((m) => m.id === model);

  return (
    <div className="border border-slate-700 rounded-xl overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 bg-slate-800 text-slate-300 text-sm hover:bg-slate-750 transition-colors"
      >
        <span className="font-medium">
          Advanced: LLM Provider
          {selected && (
            <span className="ml-2 text-slate-500 font-normal">
              ({selected.label} · {selectedModelMeta?.label ?? model})
            </span>
          )}
        </span>
        {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
      </button>

      {open && (
        <div className="bg-slate-900 p-4 space-y-3 border-t border-slate-700">
          {loadError && (
            <p className="text-red-400 text-xs">{loadError}</p>
          )}

          <p className="text-slate-500 text-xs">
            Only providers with a real API key in <code className="text-slate-400">backend/.env</code> appear
            (placeholders like <code className="text-slate-400">sk-...</code> are ignored).
            Ollama runs locally — no key needed.
          </p>

          {providers.length === 0 && !loadError && (
            <p className="text-amber-400 text-xs">
              No cloud providers configured. Add an API key to backend/.env or use Ollama.
            </p>
          )}

          <div>
            <label className="block text-slate-400 text-xs mb-1 font-medium">Provider</label>
            <select
              value={value}
              onChange={(e) => {
                const p = providers.find((p) => p.id === e.target.value);
                const defaultModel = p?.models[0]?.id ?? p?.model ?? model;
                onChange(e.target.value, defaultModel);
              }}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
            >
              {providers.map((p) => (
                <option key={p.id} value={p.id}>{p.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-slate-400 text-xs mb-1 font-medium">Model</label>
            {modelOptions.length > 0 ? (
              <>
                <select
                  value={modelOptions.some((m) => m.id === model) ? model : modelOptions[0].id}
                  onChange={(e) => onChange(value, e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
                >
                  {modelOptions.map((m) => (
                    <option key={m.id} value={m.id}>{m.label}</option>
                  ))}
                </select>
                {selectedModelMeta?.note && (
                  <p className="text-slate-500 text-xs mt-1.5">{selectedModelMeta.note}</p>
                )}
              </>
            ) : (
              <input
                value={model}
                onChange={(e) => onChange(value, e.target.value)}
                placeholder="Enter model id"
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
