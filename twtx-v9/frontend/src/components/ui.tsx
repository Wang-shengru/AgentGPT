import type { ReactNode } from "react";
import { clamp, dirClass, isNum } from "../format";

export function Panel(props: { title: ReactNode; right?: ReactNode; className?: string; children: ReactNode }) {
  return (
    <section className={`panel ${props.className ?? ""}`}>
      <header className="panel-head">
        <h2>{props.title}</h2>
        {props.right && <div className="panel-right">{props.right}</div>}
      </header>
      <div className="panel-body">{props.children}</div>
    </section>
  );
}

export function Badge({ text }: { text: string }) {
  const cls = text.includes("多") ? "up" : text.includes("空") ? "down" : "flat";
  return <span className={`badge ${cls}`}>{text}</span>;
}

const P = (cx: number, cy: number, r: number, th: number) => [cx + r * Math.cos(th), cy - r * Math.sin(th)];

function arc(cx: number, cy: number, r: number, a0: number, a1: number) {
  // angles in radians, a0 -> a1 drawn clockwise when a0 > a1
  const [x0, y0] = P(cx, cy, r, a0);
  const [x1, y1] = P(cx, cy, r, a1);
  const sweep = a0 > a1 ? 1 : 0;
  const large = Math.abs(a1 - a0) > Math.PI ? 1 : 0;
  return `M ${x0} ${y0} A ${r} ${r} 0 ${large} ${sweep} ${x1} ${y1}`;
}

/** Self-drawn SVG half gauge. ``value`` is centred on ``center`` and scaled to ±scale. */
export function Gauge(props: {
  label: string;
  value: number | null;
  scale: number;
  center?: number;
  display: string;
  sub?: ReactNode;
  scaleLabel?: (v: number) => string;
  big?: boolean;
}) {
  const { value, scale, center = 0 } = props;
  const norm = isNum(value) && scale > 0 ? clamp((value - center) / scale, -1, 1) : 0;
  const th = Math.PI * (1 - (norm + 1) / 2);
  const cx = 100, cy = 98, r = 78;
  const [nx, ny] = P(cx, cy, r - 14, th);
  const col = norm > 0 ? "var(--up)" : norm < 0 ? "var(--down)" : "var(--muted)";
  const ticks = [-1, -0.5, 0, 0.5, 1];
  const lab = props.scaleLabel ?? ((v: number) => String(Math.round(v)));
  return (
    <div className={`gauge ${props.big ? "big" : ""}`}>
      <div className="gauge-label">{props.label}</div>
      <svg viewBox="-4 -6 208 126" role="img" aria-label={`${props.label} ${props.display}`}>
        <path d={arc(cx, cy, r, Math.PI, Math.PI / 2)} className="g-track down" />
        <path d={arc(cx, cy, r, Math.PI / 2, 0)} className="g-track up" />
        {norm !== 0 && <path d={arc(cx, cy, r, Math.PI / 2, th)} stroke={col} className="g-fill" />}
        {ticks.map((t) => {
          const a = Math.PI * (1 - (t + 1) / 2);
          const [x0, y0] = P(cx, cy, r + 9, a);
          const [x1, y1] = P(cx, cy, r + 2, a);
          const [tx, ty] = t === 0 ? P(cx, cy, r + 14, a) : [cx + (t < 0 ? -r - 6 : r + 6), cy + 14];
          return (
            <g key={t}>
              <line x1={x0} y1={y0} x2={x1} y2={y1} className="g-tick" />
              {(t === -1 || t === 1 || t === 0) && (
                <text x={tx} y={ty + 3} className="g-scale" textAnchor="middle">
                  {lab(center + t * scale)}
                </text>
              )}
            </g>
          );
        })}
        <line x1={cx} y1={cy} x2={nx} y2={ny} className="g-needle" style={{ transition: "all .4s ease" }} />
        <circle cx={cx} cy={cy} r={5} className="g-hub" />
      </svg>
      <div className={`gauge-value num ${dirClass(isNum(value) ? value - center : null)}`}>{props.display}</div>
      {props.sub && <div className="gauge-sub">{props.sub}</div>}
    </div>
  );
}

/** Horizontal two-way bar centred at zero, scaled to ±scale. */
export function BiBar({ value, scale, height = 6 }: { value: number | null; scale: number; height?: number }) {
  const n = isNum(value) && scale > 0 ? clamp(value / scale, -1, 1) : 0;
  return (
    <div className="bibar" style={{ height }}>
      <div className="bibar-mid" />
      <div
        className={`bibar-fill ${n >= 0 ? "up" : "down"}`}
        style={{ left: n >= 0 ? "50%" : `${50 + n * 50}%`, width: `${Math.abs(n) * 50}%` }}
      />
    </div>
  );
}

export function Dots({ n, dir, dim }: { n: number; dir: number; dim?: boolean }) {
  const cls = dir > 0 ? "up" : dir < 0 ? "down" : "flat";
  return (
    <span className={`dots ${dim ? "dim" : ""}`} aria-label={`強度 ${n}/4`}>
      {[1, 2, 3, 4].map((i) => (
        <i key={i} className={i <= n ? `on ${cls}` : ""} />
      ))}
    </span>
  );
}

export function DirTag({ dir, available = true }: { dir: number; available?: boolean }) {
  if (!available) return <span className="dtag na">不可用</span>;
  const t = dir > 0 ? "偏多" : dir < 0 ? "偏空" : "中性";
  return <span className={`dtag ${dir > 0 ? "up" : dir < 0 ? "down" : "flat"}`}>{t}</span>;
}
