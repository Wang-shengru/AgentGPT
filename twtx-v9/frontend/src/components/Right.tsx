import type { Snapshot } from "../schema";
import { sfmt } from "../format";
import { BiBar, DirTag, Dots, Gauge, Panel } from "./ui";

export function MarketV3({ snap }: { snap: Snapshot | null }) {
  const v = snap?.v3;
  const cls = v?.verdict.includes("多") ? "up" : v?.verdict.includes("空") ? "down" : "flat";
  return (
    <Panel title="盤面現況分析 V3" className="v3" right={<span className="num muted">{snap?.ts.slice(5, 16) ?? ""}</span>}>
      <div className="v3-top">
        <Gauge
          big
          label="淨值（4 組等權・每組 ±1）"
          value={v?.net ?? null}
          scale={4}
          display={sfmt(v?.net, 2)}
          scaleLabel={(x) => (x > 0 ? `+${x}` : `${x}`)}
        />
        <div className="v3-verdict">
          <div className={`verdict ${cls}`}>{v?.verdict ?? "—"}</div>
          <div className="sentence">{v?.sentence ?? ""}</div>
          <div className="cons">
            <span>一致度</span>
            <div className="pbar"><div style={{ width: `${v?.consistency ?? 0}%` }} /></div>
            <b className="num">{v ? v.consistency.toFixed(0) : "—"}</b>
          </div>
          <div className="counts num">
            <span className="up">多 {v?.bull ?? 0}</span>
            <span className="down">空 {v?.bear ?? 0}</span>
            <span className="flat">中 {v?.neutral ?? 0}</span>
            <span className="muted">可用 {v?.n_available ?? 0}/{v?.n_items ?? 13} 項・{v?.groups_available ?? 0}/{v?.n_groups ?? 4} 組</span>
          </div>
        </div>
      </div>
      {(v?.groups ?? []).map((g) => (
        <div key={g.key} className="v3-group">
          <div className="v3-ghead">
            <span className="gname">{g.name}</span>
            <div className="gbar"><BiBar value={g.score} scale={1} height={8} /></div>
            <b className={`num ${g.score > 0 ? "up" : g.score < 0 ? "down" : "flat"}`}>{sfmt(g.score, 2)}</b>
          </div>
          {g.items.map((it) => (
            <div key={it.key} className={`v3-row ${it.voting ? "" : "nonvote"} ${it.available ? "" : "na"}`} title={it.voting ? "" : "僅顯示不投票"}>
              <DirTag dir={it.direction} available={it.available} />
              <Dots n={it.strength} dir={it.direction} dim={!it.voting} />
              <span className="v3-text">
                <span className="v3-label">{it.label}</span>
                <span className="v3-desc">{it.text}</span>
              </span>
              <span className="v3-val num">{it.display}</span>
            </div>
          ))}
        </div>
      ))}
    </Panel>
  );
}
