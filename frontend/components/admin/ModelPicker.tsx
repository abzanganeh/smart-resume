"use client"

import { useMemo } from "react"

export interface ModelCatalogEntry {
  id: string
  label: string
  note?: string
}

export type ModelCatalog = Record<string, ModelCatalogEntry[]>

const CUSTOM_OPTION = "__custom__"

export const DEFAULT_MODEL_PROVIDERS = [
  "openai",
  "anthropic",
  "gemini",
  "deepseek",
  "openrouter",
  "ollama",
] as const

const inputCls =
  "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500"

export function resolveModelSelectValue(
  provider: string,
  model: string,
  catalog: ModelCatalog,
): string {
  const models = catalog[provider] ?? []
  if (models.some((m) => m.id === model)) {
    return model
  }
  return model ? CUSTOM_OPTION : models[0]?.id ?? CUSTOM_OPTION
}

export function defaultModelForProvider(
  provider: string,
  catalog: ModelCatalog,
  currentModel?: string,
): string {
  const models = catalog[provider] ?? []
  if (currentModel && models.some((m) => m.id === currentModel)) {
    return currentModel
  }
  return models[0]?.id ?? currentModel ?? ""
}

interface ModelPickerProps {
  catalog: ModelCatalog
  provider: string
  model: string
  onProviderChange: (provider: string) => void
  onModelChange: (model: string) => void
  providers?: readonly string[]
}

export function ModelPicker({
  catalog,
  provider,
  model,
  onProviderChange,
  onModelChange,
  providers = DEFAULT_MODEL_PROVIDERS,
}: ModelPickerProps) {
  const models = catalog[provider] ?? []
  const selectValue = useMemo(
    () => resolveModelSelectValue(provider, model, catalog),
    [provider, model, catalog],
  )
  const isCustom = selectValue === CUSTOM_OPTION

  function handleProviderChange(nextProvider: string) {
    onProviderChange(nextProvider)
    onModelChange(defaultModelForProvider(nextProvider, catalog, model))
  }

  function handleModelSelectChange(value: string) {
    if (value === CUSTOM_OPTION) {
      if (!isCustom) {
        onModelChange("")
      }
      return
    }
    onModelChange(value)
  }

  return (
    <div className="grid grid-cols-2 gap-4">
      <div>
        <label className="block text-xs text-slate-400 mb-1.5">Provider</label>
        <select
          value={provider}
          onChange={(e) => handleProviderChange(e.target.value)}
          className={inputCls}
        >
          {providers.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="block text-xs text-slate-400 mb-1.5">Model</label>
        <select
          value={selectValue}
          onChange={(e) => handleModelSelectChange(e.target.value)}
          className={inputCls}
        >
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
          <option value={CUSTOM_OPTION}>Other (custom id)</option>
        </select>
        {isCustom && (
          <input
            type="text"
            required
            value={model}
            onChange={(e) => onModelChange(e.target.value)}
            className={`${inputCls} mt-2`}
            placeholder="custom-model-id"
          />
        )}
        {!isCustom && models.find((m) => m.id === model)?.note ? (
          <p className="text-[11px] text-slate-500 mt-1">
            {models.find((m) => m.id === model)?.note}
          </p>
        ) : null}
      </div>
    </div>
  )
}
