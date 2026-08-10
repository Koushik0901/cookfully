import { describe, expect, it } from "vitest";

import { canonicalDecimal, decimal6, servingDecimal } from "./decimal";

describe("canonical decimal adapters", () => {
  it("removes trailing zeroes without exponent notation", () => {
    expect(canonicalDecimal("12.340000")).toBe("12.34");
    expect(canonicalDecimal("0.000001")).toBe("0.000001");
  });

  it("rejects invalid public values", () => {
    expect(() => decimal6.parse("1e3")).toThrow();
    expect(() => servingDecimal.parse("0.000")).toThrow();
  });
});
