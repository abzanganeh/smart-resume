"use client";

import { useEffect, useState } from "react";
import {
  CheckCircle2,
  ChevronRight,
  Eye,
  EyeOff,
  ExternalLink,
  Loader2,
} from "lucide-react";
import { getLLMProviders, verifyLLMKey, type LLMModelOption, type LLMProvider } from "@/lib/api";
import { clearKey, getStoredKey, storeKey } from "@/lib/keyStore";

// ── Per-provider setup guide ────────────────────────────────────────────────

interface ProviderGuide {
  cost: string;
  freeTier: boolean;
  freeLabel?: string;
  keyLabel: string;
  keyPlaceholder: string;
  steps: string[];
  keyUrl: string;
}

const GUIDES: Record<string, ProviderGuide> = {
  gemini: {
    cost: "Free tier: 1,500 req/day",
    freeTier: true,
    freeLabel: "Free tier — no credit card",
    keyLabel: "Google AI Studio API Key",
    keyPlaceholder: "AIza...",
    keyUrl: "https://aistudio.google.com/apikey",
    steps: [
      "Go to aistudio.google.com/apikey",
      "Sign in with your Google account",
      'Click "Create API key"',
      "Copy the key and paste it below",
    ],
  },
  openrouter: {
    cost: "Free models available",
    freeTier: true,
    freeLabel: "Free models (Llama, Mistral)",
    keyLabel: "OpenRouter API Key",
    keyPlaceholder: "sk-or-...",
    keyUrl: "https://openrouter.ai/keys",
    steps: [
      "Go to openrouter.ai and create a free account",
      'Navigate to "Keys" in your dashboard',
      'Click "Create key"',
      "Copy the key and paste it below",
      "Tip: pick a free model like Llama 3.1 8B to pay nothing",
    ],
  },
  ollama: {
    cost: "100% free — runs locally",
    freeTier: true,
    freeLabel: "Completely free, no key needed",
    keyLabel: "",
    keyPlaceholder: "",
    keyUrl: "https://ollama.ai",
    steps: [
      "Download and install Ollama from ollama.ai",
      "Open a terminal and run: ollama pull llama3.1:8b",
      "Ollama runs in the background automatically",
      "No API key needed — select a model below and continue",
    ],
  },
  openai: {
    cost: "~$0.01–0.05 per resume",
    freeTier: false,
    keyLabel: "OpenAI API Key",
    keyPlaceholder: "sk-...",
    keyUrl: "https://platform.openai.com/api-keys",
    steps: [
      "Go to platform.openai.com and sign in",
      'Click your profile → "API keys"',
      'Click "Create new secret key"',
      "Copy the key immediately (shown only once)",
      "Paste it below",
    ],
  },
  anthropic: {
    cost: "~$0.01–0.08 per resume",
    freeTier: false,
    keyLabel: "Anthropic API Key",
    keyPlaceholder: "sk-ant-...",
    keyUrl: "https://console.anthropic.com/",
    steps: [
      "Go to console.anthropic.com and sign in",
      'Navigate to "API Keys" in the sidebar',
      'Click "Create Key"',
      "Copy the key and paste it below",
    ],
  },
};

// ── Component ────────────────────────────────────────────────────────────────

interface Props {
  onComplete: (provider: string, model: string) => void;
}

export default function ProviderSetup({ onComplete }: Props) {
  const [providers, setProviders] = useState<LLMProvider[]>([]);
  const [selected, setSelected] = useState<LLMProvider | null>(null);
  const [selectedModel, setSelectedModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState(false);
  const [verifyResult, setVerifyResult] = useState<{ valid: boolean; message: string } | null>(null);

  useEffect(() => {
    getLLMProviders()
      .then(({ providers: ps }) => {
        setProviders(ps);
        const stored = getStoredKey();
        if (stored) {
          const match = ps.find((p) => p.id === stored.provider) ?? null;
          setSelected(match);
          // Validate the stored model against the current catalog; fall back to
          // the catalog default if the model was retired or renamed.
          const modelStillValid = match?.models?.some((m) => m.id === stored.model) ?? false;
          setSelectedModel(modelStillValid ? stored.model : (match?.model ?? ""));
          setApiKey(stored.apiKey === "__env__" ? "" : stored.apiKey);
          setSaved(true);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  function pick(p: LLMProvider) {
    setSelected(p);
    setSelectedModel(p.model);
    setSaved(false);
    setApiKey("");
    setVerifyResult(null);
  }

  function pickModel(m: LLMModelOption) {
    setSelectedModel(m.id);
    setSaved(false);
    setVerifyResult(null);
  }

  async function handleTest() {
    if (!selected) return;
    setTesting(true);
    setVerifyResult(null);
    try {
      const result = await verifyLLMKey({
        provider: selected.id,
        model: selectedModel,
        api_key: apiKey.trim() || undefined,
      });
      setVerifyResult({ valid: result.valid, message: result.message });
    } catch {
      setVerifyResult({ valid: false, message: "Could not reach the backend. Is it running on port 8000?" });
    } finally {
      setTesting(false);
    }
  }

  function handleSave() {
    if (!selected) return;
    const keyToSave =
      apiKey.trim() || (selected.has_env_key ? "__env__" : "");
    if (!keyToSave) return;
    storeKey({ provider: selected.id, model: selectedModel, apiKey: keyToSave });
    setSaved(true);
    onComplete(selected.id, selectedModel);
  }

  function handleContinueOllama() {
    if (!selected) return;
    storeKey({ provider: selected.id, model: selectedModel, apiKey: "__env__" });
    setSaved(true);
    onComplete(selected.id, selectedModel);
  }

  function handleClear() {
    clearKey();
    setApiKey("");
    setSaved(false);
    setVerifyResult(null);
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-slate-400">
        <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading providers…
      </div>
    );
  }

  const guide = selected ? GUIDES[selected.id] : null;
  const models = selected?.models ?? [];
  const canTest = selected
    ? selected.id === "ollama" || selected.has_env_key || !!apiKey.trim()
    : false;
  const testedOk = verifyResult?.valid === true;

  return (
    <div className="space-y-6">
      {/* Provider grid */}
      <div>
        <p className="text-sm text-slate-400 mb-3">
          Choose a provider. Free options are highlighted — we recommend Gemini or Ollama to keep costs at zero.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {providers.map((p) => {
            const g = GUIDES[p.id];
            const isSelected = selected?.id === p.id;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => pick(p)}
                className={`w-full text-left rounded-xl border p-4 transition-all ${
                  isSelected
                    ? "border-violet-500 bg-violet-950/40 ring-1 ring-violet-500/40"
                    : g?.freeTier
                    ? "border-emerald-800/60 bg-emerald-950/20 hover:border-emerald-600"
                    : "border-slate-700 bg-slate-800/60 hover:border-slate-500"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <ProviderEmoji id={p.id} />
                    <div>
                      <div className="font-semibold text-slate-100 text-sm">{p.label}</div>
                      <div className="text-xs text-slate-400 mt-0.5">{g?.cost}</div>
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1.5 shrink-0">
                    {g?.freeTier && (
                      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-900/60 text-emerald-300 border border-emerald-700 whitespace-nowrap">
                        {g.freeLabel}
                      </span>
                    )}
                    {p.has_env_key && (
                      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-violet-900/60 text-violet-300 border border-violet-700 whitespace-nowrap">
                        Server key ready
                      </span>
                    )}
                    {isSelected && (
                      <CheckCircle2 className="h-4 w-4 text-violet-400" />
                    )}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Setup guide */}
      {selected && guide && (
        <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden">
          {/* Guide header */}
          <div className="flex items-center gap-3 px-5 py-4 border-b border-slate-700 bg-slate-800/50">
            <ProviderEmoji id={selected.id} size="lg" />
            <div>
              <div className="font-semibold text-slate-100">{selected.label}</div>
              <div className="text-xs text-slate-400">{guide.cost}</div>
            </div>
          </div>

          <div className="p-5 space-y-5">
            {/* Step-by-step instructions */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-sm font-semibold text-slate-200">
                  {selected.id === "ollama" ? "How to set up Ollama" : "How to get your API key"}
                </h4>
                {guide.keyUrl && (
                  <a
                    href={guide.keyUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 text-xs text-violet-400 hover:text-violet-300 transition-colors"
                  >
                    Open dashboard <ExternalLink className="h-3 w-3" />
                  </a>
                )}
              </div>
              <ol className="space-y-2">
                {guide.steps.map((step, i) => (
                  <li key={i} className="flex items-start gap-3 text-sm text-slate-300">
                    <span className="shrink-0 w-5 h-5 rounded-full bg-slate-700 flex items-center justify-center text-[11px] font-bold text-slate-400 mt-0.5">
                      {i + 1}
                    </span>
                    {step}
                  </li>
                ))}
              </ol>
            </div>

            {/* Model picker */}
            {models.length > 0 && (
              <div>
                <label className="text-xs font-medium text-slate-400 block mb-2">Model</label>
                <div className="grid grid-cols-1 gap-1.5">
                  {models.map((m) => (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => pickModel(m)}
                      className={`flex items-start gap-3 px-3 py-2.5 rounded-lg border text-left transition-all ${
                        selectedModel === m.id
                          ? "border-violet-500 bg-violet-950/30"
                          : "border-slate-700 hover:border-slate-500"
                      }`}
                    >
                      <div
                        className={`mt-0.5 w-3.5 h-3.5 rounded-full border-2 shrink-0 ${
                          selectedModel === m.id
                            ? "border-violet-500 bg-violet-500"
                            : "border-slate-600"
                        }`}
                      />
                      <div>
                        <div className="text-sm font-medium text-slate-200">{m.label}</div>
                        {m.note && (
                          <div className="text-xs text-slate-500 mt-0.5">{m.note}</div>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Key input — not needed for Ollama */}
            {selected.id !== "ollama" && !selected.has_env_key && (
              <div>
                <label className="text-xs font-medium text-slate-400 block mb-2">
                  {guide.keyLabel}
                </label>
                <div className="relative">
                  <input
                    type={showKey ? "text" : "password"}
                    value={apiKey}
                    onChange={(e) => { setApiKey(e.target.value); setSaved(false); setVerifyResult(null); }}
                    placeholder={guide.keyPlaceholder}
                    className="w-full pr-10 px-3 py-2.5 rounded-lg border border-slate-700 bg-slate-800 text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-violet-500 font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey((s) => !s)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                  >
                    {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <p className="mt-2 text-[11px] text-slate-500 leading-relaxed">
                  Stored in your browser's <code className="text-slate-400">sessionStorage</code> only.
                  Disappears when the tab closes. Never logged or saved by this server.
                </p>
                {/* Test button — directly under key input */}
                <button
                  type="button"
                  onClick={handleTest}
                  disabled={testing || !apiKey.trim()}
                  className="mt-3 w-full flex items-center justify-center gap-2 py-2.5 rounded-lg border border-violet-600 text-violet-300 hover:bg-violet-950/40 text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {testing ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" /> Testing key…
                    </>
                  ) : (
                    "Test API key"
                  )}
                </button>
              </div>
            )}

            {/* Server-configured key — test before continue */}
            {selected.has_env_key && selected.id !== "ollama" && (
              <button
                type="button"
                onClick={handleTest}
                disabled={testing}
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg border border-violet-600 text-violet-300 hover:bg-violet-950/40 text-sm font-medium transition-colors disabled:opacity-40"
              >
                {testing ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Testing server key…
                  </>
                ) : (
                  "Test API key"
                )}
              </button>
            )}

            {/* Server-configured key notice */}
            {selected.has_env_key && (
              <div className="flex items-start gap-2 p-3 rounded-lg bg-violet-950/30 border border-violet-800/50 text-sm text-violet-300">
                <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" />
                A server key is already configured for {selected.label}. You can use it as-is or
                paste your own key above to override.
              </div>
            )}

            {/* Verify result */}
            {verifyResult && (
              <div
                className={`flex items-start gap-2 p-3 rounded-lg text-sm border ${
                  verifyResult.valid
                    ? "bg-emerald-950/30 border-emerald-800/50 text-emerald-300"
                    : "bg-red-950/30 border-red-800/50 text-red-300"
                }`}
              >
                {verifyResult.valid ? (
                  <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" />
                ) : (
                  <span className="shrink-0 mt-0.5 font-bold">✕</span>
                )}
                {verifyResult.message}
              </div>
            )}

            {!testedOk && selected && canTest && !testing && (
              <p className="text-xs text-slate-500 text-center">
                Test your key before continuing to upload your resume.
              </p>
            )}

            {/* Continue — only enabled after a successful test */}
            {selected.id === "ollama" ? (
              <div className="space-y-2">
                <button
                  type="button"
                  onClick={handleTest}
                  disabled={testing}
                  className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg border border-violet-600 text-violet-300 hover:bg-violet-950/40 text-sm font-medium transition-colors disabled:opacity-40"
                >
                  {testing ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" /> Testing Ollama…
                    </>
                  ) : (
                    "Test connection"
                  )}
                </button>
                <button
                  type="button"
                  onClick={handleContinueOllama}
                  disabled={!testedOk}
                  className="w-full flex items-center justify-center gap-2 py-3 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors"
                >
                  Continue to upload resume <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            ) : (
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={!testedOk}
                  className="flex-1 flex items-center justify-center gap-2 py-3 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors"
                >
                  Continue to upload resume <ChevronRight className="h-4 w-4" />
                </button>
                {saved && (
                  <button
                    type="button"
                    onClick={handleClear}
                    className="px-3 py-3 rounded-lg border border-slate-700 text-slate-400 hover:text-red-400 hover:border-red-800 text-xs transition-colors"
                  >
                    Clear
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {!selected && (
        <p className="text-center text-slate-500 text-sm py-4">
          ← Pick a provider above to see setup instructions
        </p>
      )}
    </div>
  );
}

function ProviderEmoji({ id, size = "sm" }: { id: string; size?: "sm" | "lg" }) {
  const icons: Record<string, string> = {
    openai: "⚡",
    anthropic: "🧠",
    gemini: "✨",
    openrouter: "🔀",
    ollama: "🦙",
  };
  return (
    <span className={size === "lg" ? "text-2xl" : "text-xl"} aria-hidden>
      {icons[id] ?? "🤖"}
    </span>
  );
}
