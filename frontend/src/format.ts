/** Indian digit grouping: 118500 -> ₹1,18,500 */
export function inr(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const neg = n < 0;
  const s = Math.round(Math.abs(n)).toString();
  let out = s;
  if (s.length > 3) {
    let head = s.slice(0, -3);
    const parts: string[] = [];
    while (head.length > 2) { parts.unshift(head.slice(-2)); head = head.slice(0, -2); }
    if (head) parts.unshift(head);
    out = [...parts, s.slice(-3)].join(",");
  }
  return (neg ? "-" : "") + "₹" + out;
}

/** Compact lakh/crore form: 3280000 -> ₹32.8L, 12000000 -> ₹1.20Cr */
export function lakh(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const a = Math.abs(n), sign = n < 0 ? "-" : "";
  if (a >= 1e7) return `${sign}₹${(a / 1e7).toFixed(2)}Cr`;
  if (a >= 1e5) return `${sign}₹${(a / 1e5).toFixed(1)}L`;
  if (a >= 1e3) return `${sign}₹${(a / 1e3).toFixed(1)}K`;
  return `${sign}₹${Math.round(a)}`;
}

export const pct = (x: number | null | undefined, d = 1) => (x === null || x === undefined ? "—" : `${(x * 100).toFixed(d)}%`);
export const humanize = (s: string) => s.replace(/_/g, " ").toLowerCase().replace(/^\w|\s\w/g, (c) => c.toUpperCase());
export const shortTime = (iso: string) => new Date(iso + (iso.endsWith("Z") ? "" : "Z")).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
