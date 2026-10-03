import { describe, expect, it } from "vitest";
import { renderToString } from "react-dom/server";
import Landing from "./pages/Landing";
import { Badge, Metric, ErrorBox } from "./components/ui";

describe("render smoke", () => {
  it("landing page shows the brand and CTA", () => {
    const html = renderToString(<Landing />);
    expect(html).toContain("RECLAIM");
    expect(html).toContain("OPEN COMMAND CENTER");
    expect(html).toContain("Recover the right revenue");
    expect(html).toContain("DEMO / SIMULATED");
  });
  it("ui primitives render", () => {
    expect(renderToString(<Metric label="Recovered" value="₹14.7L" />)).toContain("₹14.7L");
    expect(renderToString(<Badge kind="BLOCK">BLOCK</Badge>)).toContain("BLOCK");
    expect(renderToString(<ErrorBox message="boom" />)).toContain("boom");
  });
});
