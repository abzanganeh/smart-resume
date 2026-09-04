import { describe, it } from "node:test"
import assert from "node:assert/strict"
import {
  applySelectAll,
  editableStepIds,
  selectAllState,
  toggleStepSelection,
} from "@/lib/admin/tierStepSelection"

const PINS = [
  { step: "phase3_rewrite", editable: true },
  { step: "chat", editable: true },
  { step: "company_intel", editable: false },
  { step: "phase3_truthfulness", editable: false },
]

describe("tierStepSelection", () => {
  it("editableStepIds includes only editable rows", () => {
    assert.deepEqual(editableStepIds(PINS), ["phase3_rewrite", "chat"])
  })

  it("select-all checks only editable rows", () => {
    const selected = applySelectAll(new Set(), PINS, true)
    assert.deepEqual([...selected].sort(), ["chat", "phase3_rewrite"])
    assert.equal(selected.has("company_intel"), false)
    assert.equal(selected.has("phase3_truthfulness"), false)
  })

  it("select-all unchecked clears editable selections only", () => {
    const selected = applySelectAll(new Set(["phase3_rewrite", "chat", "other"]), PINS, false)
    assert.equal(selected.size, 1)
    assert.equal(selected.has("other"), true)
  })

  it("indeterminate when some but not all editable rows selected", () => {
    assert.equal(selectAllState(new Set(), PINS), "unchecked")
    assert.equal(selectAllState(new Set(["phase3_rewrite"]), PINS), "indeterminate")
    assert.equal(
      selectAllState(new Set(["phase3_rewrite", "chat"]), PINS),
      "checked",
    )
    assert.equal(selectAllState(new Set(["company_intel"]), PINS), "unchecked")
  })

  it("toggleStepSelection adds and removes individual steps", () => {
    let selected = toggleStepSelection(new Set(), "chat")
    assert.deepEqual([...selected], ["chat"])
    selected = toggleStepSelection(selected, "chat")
    assert.equal(selected.size, 0)
  })

  it("plan change clears selection via empty set", () => {
    const beforePlanChange = applySelectAll(new Set(), PINS, true)
    const afterPlanChange = new Set<string>()
    assert.equal(beforePlanChange.size, 2)
    assert.equal(afterPlanChange.size, 0)
  })
})
