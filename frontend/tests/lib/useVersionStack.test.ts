import { describe, expect, it } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useVersionStack } from "@/lib/useVersionStack";

describe("useVersionStack", () => {
  it("tracks undo and redo across edits", () => {
    const { result } = renderHook(() => useVersionStack({ value: 0 }));

    act(() => {
      result.current.push({ value: 1 });
    });
    act(() => {
      result.current.push({ value: 2 });
    });

    expect(result.current.present).toEqual({ value: 2 });
    expect(result.current.canUndo).toBe(true);

    let undone: { value: number } | null = null;
    act(() => {
      undone = result.current.undo();
    });
    expect(undone).toEqual({ value: 1 });
    expect(result.current.present).toEqual({ value: 1 });
    expect(result.current.canRedo).toBe(true);

    act(() => {
      result.current.redo();
    });
    expect(result.current.present).toEqual({ value: 2 });
  });

  it("reset clears history", () => {
    const { result } = renderHook(() => useVersionStack({ value: 0 }));

    act(() => {
      result.current.push({ value: 1 });
      result.current.reset({ value: 99 });
    });

    expect(result.current.present).toEqual({ value: 99 });
    expect(result.current.canUndo).toBe(false);
    expect(result.current.canRedo).toBe(false);
  });
});
