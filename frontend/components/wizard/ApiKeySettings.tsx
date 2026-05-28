"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, ChevronDown, Eye, EyeOff, ExternalLink, Key, Trash2, Zap } from "lucide-react";
import { getLLMProviders, LLMModelOption, LLMProvider } from "@/lib/api";
import { clearKey, getStoredKey, storeKey } from "@/lib/keyStore";

interface Props {
  /** Called after user saves a key so parent can re-render with updated selection */
  onChange?: (provider: string, model: string) => void;
}

export default function ApiKeySettings({ onChange }: Props) {
  const [providers, setProviders] = useState<LLMProvider[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<LLMProvider | null>(null);
  const [selectedModel, setSelectedModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [providerOpen, setProviderOpen] = useState(false);
  const [modelOpen, setModelOpen] = useState(false);

  useEffect(() => {
    getLLMProviders()
      .then(({ providers: ps }) => {
        setProviders(ps);

        // Pre-fill from sessionStorage if a key was previously saved
        const stored = getStoredKey();
        if (stored) {
          const match = ps.find((p) => p.id === stored.provider) ?? ps[0];
          setSelectedProvider(match);
          setSelectedModel(stored.model || match?.model || "");
          setApiKey(stored.apiKey);
          setSaved(true);
        } else {
          // Pre-select the first provider that already has an env key
          const envProvider = ps.find((p) => p.has_env_key) ?? ps[0];
          if (envProvider) {
            setSelectedProvider(envProvider);
            setSelectedModel(envProvider.model);
          }
        }
      })
      .finally(() => setLoading(false));
  }, []);

  function pickProvider(p: LLMProvider) {
    setSelectedProvider(p);
    setSelectedModel(p.model);
    setSaved(false);
    setProviderOpen(false);
  }

  function pickModel(m: LLMModelOption) {
    setSelectedModel(m.id);
    setSaved(false);
    setModelOpen(false);
  }

  function handleSave() {
    if (!selectedProvider) return;
    const keyToSave = apiKey.trim() || (selectedProvider.has_env_key ? "__env__" : "");
    if (!keyToSave || keyToSave === "__env__") {
      // No user key — clear stored and use env
      clearKey();
    } else {
      storeKey({ provider: selectedProvider.id, model: selectedModel, apiKey: keyToSave });
    }
    setSaved(true);
    onChange?.(selectedProvider.id, selectedModel);
  }

  function handleClear() {
    clearKey();
    setApiKey("");
    setSaved(false);
  }

  if (loading) {
    return (
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-700 p-4 animate-pulse">
        <div className="h-4 bg-zinc-200 dark:bg-zinc-700 rounded w-1/3 mb-3" />
        <div className="h-10 bg-zinc-100 dark:bg-zinc-800 rounded mb-3" />
        <div className="h-10 bg-zinc-100 dark:bg-zinc-800 rounded" />
      </div>
    );
  }

  const models = selectedProvider?.models ?? [];
  const currentModel = models.find((m) => m.id === selectedModel);
  const needsUserKey = selectedProvider?.requires_key && !selectedProvider?.has_env_key;

  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 p-5 space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Key className="h-4 w-4 text-violet-500" />
        <h3 className="font-semibold text-sm text-zinc-800 dark:text-zinc-100">AI Provider &amp; Key</h3>
        {saved && (
          <span className="ml-auto flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400 font-medium">
            <CheckCircle2 className="h-3.5 w-3.5" /> Active
          </span>
        )}
      </div>

      {/* Provider picker */}
      <div className="relative">
        <label className="text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-1 block">Provider</label>
        <button
          type="button"
          onClick={() => { setProviderOpen((o) => !o); setModelOpen(false); }}
          className="w-full flex items-center justify-between px-3 py-2.5 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 text-sm text-zinc-800 dark:text-zinc-100 hover:border-violet-400 transition-colors"
        >
          <span className="flex items-center gap-2">
            {selectedProvider ? (
              <>
                <ProviderIcon id={selectedProvider.id} />
                {selectedProvider.label}
                {selectedProvider.has_env_key && (
                  <span className="ml-1 px-1.5 py-0.5 text-[10px] font-semibold rounded bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300">
                    .env key
                  </span>
                )}
              </>
            ) : (
              "Select provider…"
            )}
          </span>
          <ChevronDown className="h-4 w-4 text-zinc-400" />
        </button>

        {providerOpen && (
          <div className="absolute z-20 mt-1 w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 shadow-lg divide-y divide-zinc-100 dark:divide-zinc-800 overflow-hidden">
            {providers.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => pickProvider(p)}
                className="w-full flex items-center gap-3 px-3 py-2.5 text-sm text-left hover:bg-violet-50 dark:hover:bg-violet-900/20 text-zinc-700 dark:text-zinc-200"
              >
                <ProviderIcon id={p.id} />
                <span className="flex-1">{p.label}</span>
                {p.has_env_key && (
                  <span className="px-1.5 py-0.5 text-[10px] font-semibold rounded bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300">
                    configured
                  </span>
                )}
                {!p.requires_key && (
                  <span className="px-1.5 py-0.5 text-[10px] font-semibold rounded bg-sky-100 dark:bg-sky-900/40 text-sky-700 dark:text-sky-300">
                    free
                  </span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Model picker */}
      {models.length > 0 && (
        <div className="relative">
          <label className="text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-1 block">Model</label>
          <button
            type="button"
            onClick={() => { setModelOpen((o) => !o); setProviderOpen(false); }}
            className="w-full flex items-center justify-between px-3 py-2.5 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 text-sm text-zinc-800 dark:text-zinc-100 hover:border-violet-400 transition-colors"
          >
            <span>{currentModel?.label ?? selectedModel}</span>
            <ChevronDown className="h-4 w-4 text-zinc-400" />
          </button>

          {modelOpen && (
            <div className="absolute z-20 mt-1 w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 shadow-lg overflow-hidden">
              {models.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => pickModel(m)}
                  className="w-full flex flex-col px-3 py-2.5 text-sm text-left hover:bg-violet-50 dark:hover:bg-violet-900/20 text-zinc-700 dark:text-zinc-200"
                >
                  <span className="font-medium">{m.label}</span>
                  {m.note && <span className="text-xs text-zinc-400 mt-0.5">{m.note}</span>}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* API Key input — shown when provider needs a key not in .env */}
      {selectedProvider?.requires_key && (
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
              {selectedProvider.has_env_key ? "API Key (optional override)" : "API Key"}
            </label>
            {selectedProvider.key_url && (
              <a
                href={selectedProvider.key_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-[11px] text-violet-500 hover:text-violet-700 transition-colors"
              >
                Get key <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>

          <div className="relative">
            <input
              type={showKey ? "text" : "password"}
              value={apiKey}
              onChange={(e) => { setApiKey(e.target.value); setSaved(false); }}
              placeholder={
                selectedProvider.has_env_key
                  ? "Leave blank to use server .env key"
                  : `Paste your ${selectedProvider.label} API key…`
              }
              className="w-full pr-10 px-3 py-2.5 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 text-sm text-zinc-800 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-violet-400 font-mono"
            />
            <button
              type="button"
              onClick={() => setShowKey((s) => !s)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600"
            >
              {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>

          {needsUserKey && !apiKey && (
            <p className="mt-1.5 text-xs text-amber-600 dark:text-amber-400">
              A key is required for this provider. It stays in your browser only — never stored on the server.
            </p>
          )}
        </div>
      )}

      {/* Save / Clear */}
      <div className="flex gap-2 pt-1">
        <button
          type="button"
          onClick={handleSave}
          disabled={needsUserKey && !apiKey.trim()}
          className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg bg-violet-600 hover:bg-violet-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors"
        >
          <Zap className="h-4 w-4" />
          {saved ? "Update" : "Use this provider"}
        </button>

        {(apiKey || saved) && (
          <button
            type="button"
            onClick={handleClear}
            title="Remove stored key"
            className="px-3 py-2.5 rounded-lg border border-zinc-200 dark:border-zinc-700 hover:bg-red-50 dark:hover:bg-red-900/20 text-zinc-500 hover:text-red-600 transition-colors"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>

      <p className="text-[11px] text-zinc-400 dark:text-zinc-500 leading-relaxed">
        Your key is stored in <strong>sessionStorage</strong> only — it disappears when you close this tab
        and is never logged or persisted by the server.
      </p>
    </div>
  );
}

function ProviderIcon({ id }: { id: string }) {
  const icons: Record<string, string> = {
    openai: "⚡",
    anthropic: "🧠",
    gemini: "✨",
    openrouter: "🔀",
    ollama: "🦙",
  };
  return <span className="text-base leading-none">{icons[id] ?? "🤖"}</span>;
}
