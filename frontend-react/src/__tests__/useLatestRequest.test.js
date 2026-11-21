import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import useLatestRequest from "../hooks/useLatestRequest";

describe("useLatestRequest", () => {
  it("only keeps the most recent request current", () => {
    const { result, rerender } = renderHook(() => useLatestRequest());
    const first = result.current.begin();
    expect(first()).toBe(true);

    const second = result.current.begin();
    expect(first()).toBe(false);
    expect(second()).toBe(true);

    result.current.invalidate();
    expect(second()).toBe(false);

    const tracker = result.current;
    rerender();
    expect(result.current).toBe(tracker);
  });
});
