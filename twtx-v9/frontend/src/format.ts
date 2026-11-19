export const isNum = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);

export function fmt(x: number | null | undefined, nd = 0): string {
  if (!isNum(x)) return "—";
  return x.toLocaleString("en-US", { minimumFractionDigits: nd, maximumFractionDigits: nd });
}

export function sfmt(x: number | null | undefined, nd = 0, suffix = ""): string {
  if (!isNum(x)) return "—";
  const s = x > 0 ? "+" : x < 0 ? "−" : "±";
  return `${s}${fmt(Math.abs(x), nd)}${suffix}`;
}

/** Taiwan convention: red = up / buy-side, green = down / sell-side. */
export function dirClass(x: number | null | undefined): string {
  if (!isNum(x) || x === 0) return "flat";
  return x > 0 ? "up" : "down";
}

export function hms(total: number): string {
  const s = Math.max(0, Math.floor(total));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  return [h, m, ss].map((v) => String(v).padStart(2, "0")).join(":");
}

export const clamp = (x: number, a: number, b: number) => Math.max(a, Math.min(b, x));
