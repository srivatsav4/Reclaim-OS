import { describe, expect, it } from "vitest";
import { humanize, inr, lakh, pct } from "./format";

describe("format", () => {
  it("groups rupees the Indian way", () => {
    expect(inr(118500)).toBe("₹1,18,500");
    expect(inr(480000)).toBe("₹4,80,000");
    expect(inr(999)).toBe("₹999");
    expect(inr(10000000)).toBe("₹1,00,00,000");
    expect(inr(-2500)).toBe("-₹2,500");
  });
  it("formats lakh and crore", () => {
    expect(lakh(3280000)).toBe("₹32.8L");
    expect(lakh(12000000)).toBe("₹1.20Cr");
    expect(lakh(4500)).toBe("₹4.5K");
  });
  it("handles null and percentages", () => {
    expect(inr(null)).toBe("—");
    expect(pct(0.2589)).toBe("25.9%");
    expect(humanize("RETRY_PAYMENT")).toBe("Retry Payment");
  });
});
