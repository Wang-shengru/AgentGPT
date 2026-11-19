import type { Level, Snapshot } from "../schema";
import { clamp, dirClass, fmt, isNum, sfmt } from "../format";
import { BiBar, Panel } from "./ui";

const ROW_H = 22;

/** Key levels sorted high→low; rows are absolutely positioned so re-ordering animates. */
export function KeyLevels({ levels }: { levels: Level[] }) {
  return (
    <Panel title="關鍵價位・距現價" className="levels">
      <div className="lv-list" style={{ height: levels.length * ROW_H }}>
        {levels.map((l, i) => {
          const isPx = l.key === "price";
          const cls = isPx ? "price" : (l.dist ?? 0) > 0 ? "up" : (l.dist ?? 0) < 0 ? "down" : "flat";
          return (
            <div key={l.key} className={`lv-row ${cls}`} style={{ transform: `translateY(${i * ROW_H}px)` }}>
              <span className="lv-label">{l.label}</span>
              <span className="lv-price num">{fmt(l.price, isPx ? 0 : 1)}</span>
              <span className="lv-dist num">{isPx ? "現價" : sfmt(l.dist, 0)}</span>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

function Slope({ s }: { s: number | null }) {
  if (!isNum(s)) return <span className="muted">—</span>;
  return <span className={dirClass(s)}>{s > 0 ? "▲" : s < 0 ? "▼" : "＝"}{fmt(Math.abs(s), 2)}</span>;
}

function labelCls(t: string) {
  return t.includes("多") ? "up" : t.includes("空") ? "down" : "flat";
}

export function TechCards({ snap }: { snap: Snapshot | null }) {
  const t = snap?.tech;
  const b = t?.boll;
  const m = t?.macd;
  const [s5, l5] = (t?.ma5_label ?? "—/—").split("/");
  return (
    <div className="tech">
      <Panel title="5K 均線・斜率" className="tcard" right={<span className="tags"><span className={`tag ${labelCls(s5)}`}>{s5}</span><span className={`tag ${labelCls(l5)}`}>{l5}</span></span>}>
        <table className="ma">
          <tbody>
            {(t?.ma5 ?? []).map((r) => (
              <tr key={r.n}>
                <th>{r.n}ma</th>
                <td className="num">{fmt(r.value, 1)}</td>
                <td className="num"><Slope s={r.slope} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
      <Panel title="60K 均線・斜率" className="tcard" right={<span className={`tag ${labelCls(t?.ma60_label ?? "")}`}>{t?.ma60_label ?? "—"}</span>}>
        <table className="ma">
          <tbody>
            {(t?.ma60 ?? []).map((r) => (
              <tr key={r.n}>
                <th>{r.n}ma</th>
                <td className="num">{fmt(r.value, 1)}</td>
                <td className="num"><Slope s={r.slope} /></td>
              </tr>
            ))}
            <tr>
              <th>K 收</th>
              <td className="num">{fmt(t?.ma60_close)}</td>
              <td />
            </tr>
          </tbody>
        </table>
      </Panel>
      <Panel title="5K 布林 20・2SD" className="tcard" right={<span className="tag">帶寬 {b ? `${b.width.toFixed(2)}%` : "—"}</span>}>
        <div className="kvrow num"><span>%B</span><b className={b ? (b.pct_b >= 0.5 ? "up" : "down") : ""}>{b ? b.pct_b.toFixed(2) : "—"}</b></div>
        <div className="pbar"><div style={{ width: `${b ? clamp(b.pct_b, 0, 1) * 100 : 0}%` }} /><i style={{ left: "50%" }} /></div>
        <table className="ma">
          <tbody>
            <tr><th>上軌</th><td className="num up">{fmt(b?.upper, 1)}</td></tr>
            <tr><th>中軌</th><td className="num">{fmt(b?.mid, 1)}</td></tr>
            <tr><th>下軌</th><td className="num down">{fmt(b?.lower, 1)}</td></tr>
          </tbody>
        </table>
      </Panel>
      <Panel title="5K MACD 12/26/9" className="tcard" right={m ? <span className={`tag ${m.dif >= m.dea ? "up" : "down"}`}>DIF 在{m.dif >= m.dea ? "上" : "下"}</span> : null}>
        <table className="ma">
          <tbody>
            <tr><th>DIF</th><td className={`num ${dirClass(m?.dif)}`}>{sfmt(m?.dif, 2)}</td></tr>
            <tr><th>DEA</th><td className={`num ${dirClass(m?.dea)}`}>{sfmt(m?.dea, 2)}</td></tr>
            <tr><th>OSC</th><td className={`num ${dirClass(m?.osc)}`}>{sfmt(m?.osc, 2)}</td></tr>
          </tbody>
        </table>
        <BiBar value={m?.osc ?? null} scale={Math.max(Math.abs(m?.osc ?? 0), Math.abs(m?.osc_prev ?? 0), 1) * 1.6} height={10} />
      </Panel>
    </div>
  );
}
