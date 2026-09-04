/** Pure helpers for tier step bulk-selection on /admin/llm. */

export type SelectAllState = "unchecked" | "checked" | "indeterminate"

export interface TierStepPinLike {
  step: string
  editable: boolean
}

export function editableStepIds(pins: TierStepPinLike[]): string[] {
  return pins.filter((pin) => pin.editable).map((pin) => pin.step)
}

export function selectAllState(
  selected: ReadonlySet<string>,
  pins: TierStepPinLike[],
): SelectAllState {
  const editable = editableStepIds(pins)
  if (editable.length === 0) return "unchecked"
  const selectedEditable = editable.filter((step) => selected.has(step))
  if (selectedEditable.length === 0) return "unchecked"
  if (selectedEditable.length === editable.length) return "checked"
  return "indeterminate"
}

export function applySelectAll(
  selected: ReadonlySet<string>,
  pins: TierStepPinLike[],
  checked: boolean,
): Set<string> {
  const editable = editableStepIds(pins)
  if (checked) {
    return new Set(editable)
  }
  const next = new Set(selected)
  for (const step of editable) next.delete(step)
  return next
}

export function editableSelectedSteps(
  selected: ReadonlySet<string>,
  pins: TierStepPinLike[],
): string[] {
  const editable = new Set(editableStepIds(pins))
  return [...selected].filter((step) => editable.has(step))
}

export function toggleStepSelection(
  selected: ReadonlySet<string>,
  step: string,
): Set<string> {
  const next = new Set(selected)
  if (next.has(step)) next.delete(step)
  else next.add(step)
  return next
}

/** Clears bulk selection when the admin switches plan_code tabs. */
export function selectionAfterPlanChange(
  _planCode: string,
  _previous: ReadonlySet<string>,
): Set<string> {
  return new Set()
}
