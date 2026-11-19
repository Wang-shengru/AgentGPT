import type { FlowProduct, Opening8, PatternCell, Snapshot } from "../schema";
import { dirClass, fmt, isNum, sfmt } from "../format";
import { Badge, BiBar, Gauge, Panel } from "./ui";

const SHORT: Record<string, string> = {
  晨星: "晨星", 夜星: "夜星", 多頭吞噬: "多吞", 空頭吞噬: "空吞", 多頭孕線: "多孕", 空頭孕線: "空孕",
  錘子: "錘子", 倒錘: "倒錘", 上吊: "上吊", 射擊之星: "射星", 十字: "十字",
};

const k = (v: number) => (Math.abs(v) >= 10000 ? `${(v / 1000).toFixed(0)}k` : Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(1)}k` : `${Math.round(v)}`);

export function OrderFlow({ snap }: { snap: Snapshot | null }) {
  const f = snap?.flow.txf;
  const ratio = f?.buy_ratio ?? null;
  return (
    <Panel title="委買賣動能 ORDER FLOW・TXF" right={<Badge text={snap?.flow.badge ?? "中性"} />} className="orderflow">
      <div className="gauges">
        <Gauge
          label="TxDelta 筆數差"
          value={f?.tx_delta ?? null}
          scale={f?.scale_tx ?? 1}
          display={sfmt(f?.tx_delta)}
          scaleLabel={k}
          sub={<><span className="up">買 {fmt(f?.tx_buy)}</span> / <span className="down">賣 {fmt(f?.tx_sell)}</span> 筆</>}
        />
        <Gauge
          label="VoDelta 口數差"
          value={f?.vo_delta ?? null}
          scale={f?.scale_vo ?? 1}
          display={sfmt(f?.vo_delta)}
          scaleLabel={k}
          sub={<><span className="up">買 {fmt(f?.vo_buy)}</span> / <span className="down">賣 {fmt(f?.vo_sell)}</span> 口・已扣開盤</>}
        />
        <Gauge
          label="IoDelta 委買賣差"
          value={f?.io_delta ?? null}
          scale={f?.scale_io ?? 1}
          display={sfmt(f?.io_delta)}
          scaleLabel={k}
          sub={<>委買 {fmt(f?.bid_total)} − 委賣 {fmt(f?.ask_total)}</>}
        />
        <Gauge
          label="主動買比 %"
          value={ratio}
          center={50}
          scale={f?.scale_ratio ?? 5}
          display={isNum(ratio) ? `${ratio.toFixed(1)}%` : "—"}
          scaleLabel={(v) => `${v.toFixed(0)}%`}
          sub={<span title={`交易所欄位交叉驗證 ${isNum(f?.buy_ratio_exchange) ? f!.buy_ratio_exchange!.toFixed(1) + "%" : "—"}`}>中心 50%・扣開盤</span>}
        />
      </div>
      <p className="note">尺=本時段極值（只放大不縮小），換盤歸零｜紅=偏買、綠=偏賣</p>
    </Panel>
  );
}

export function ThreeProducts({ snap }: { snap: Snapshot | null }) {
  const rows: [string, FlowProduct | undefined][] = [
    ["TXF", snap?.flow.txf],
    ["MXF", snap?.flow.mxf],
    ["TMF", snap?.flow.tmf],
  ];
  return (
    <Panel title="三商品 TXD・VOD・IOD" className="three">
      <table className="tri">
        <thead>
          <tr>
            <th />
            <th>TxDelta</th>
            <th>VoDelta</th>
            <th>IoDelta</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, f]) => (
            <tr key={name}>
              <th>{name}</th>
              {([
                [f?.tx_delta, f?.scale_tx],
                [f?.vo_delta, f?.scale_vo],
                [f?.io_delta, f?.scale_io],
              ] as const).map(([v, s], i) => (
                <td key={i}>
                  <div className={`num ${dirClass(v ?? null)}`}>{sfmt(v ?? null)}</div>
                  <BiBar value={v ?? null} scale={s ?? 1} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function Strip({ name, cells }: { name: string; cells: PatternCell[] }) {
  const pad = Array.from({ length: Math.max(0, 12 - cells.length) });
  return (
    <div className="strip">
      <div className="strip-name">{name}</div>
      <div className="strip-cells">
        {pad.map((_, i) => (
          <div key={`p${i}`} className="cell empty" />
        ))}
        {cells.map((c) => (
          <div key={c.t} className="cell-wrap" title={`${c.t}${c.pattern ? "｜" + c.pattern : ""}｜實體佔距 ${(c.body_ratio * 100).toFixed(0)}%`}>
            <div className={`cell ${c.color}`} />
            {c.pattern && (
              <div className={`cell-pat ${c.bias > 0 ? "up" : c.bias < 0 ? "down" : "flat"}`}>
                <b>{SHORT[c.pattern] ?? c.pattern.slice(0, 2)}</b>
                <span>{c.t.slice(-5)}</span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export function PatternStrips({ snap }: { snap: Snapshot | null }) {
  const p = snap?.patterns;
  const hit = p?.latest;
  return (
    <Panel
      title="K 棒型態"
      className="patterns"
      right={<span className="muted small">最近命中：{hit ? `${hit.tf} ${hit.t.slice(0, 5)} ${hit.pattern}` : "—"}</span>}
    >
      <Strip name="5K" cells={p?.k5 ?? []} />
      <Strip name="60K" cells={p?.k60 ?? []} />
      <Strip name="日/夜K" cells={p?.kS ?? []} />
    </Panel>
  );
}

export function OpeningEight({ o }: { o: Opening8 | undefined }) {
  const cls = o?.tendency?.includes("多") ? "up" : o?.tendency?.includes("空") ? "down" : "flat";
  return (
    <Panel title="開盤八法（現貨前三根）" className="open8" right={<span className="muted small num">{o?.date ?? ""}</span>}>
      <div className="o8-head">
        <div className={`o8-name ${cls}`}>{o?.name ?? "—"}</div>
        <div className={`o8-tend ${cls}`}>{o?.tendency ?? "—"}</div>
      </div>
      <div className="o8-desc muted">{o?.desc}</div>
      <div className="o8-grid">
        <div className="o8-cell">
          <span className="muted">昨收</span>
          <b className="num">{fmt(o?.prev_close, 2)}</b>
          <span className="muted small">現貨</span>
        </div>
        {[0, 1, 2].map((i) => {
          const b = o?.bars?.[i];
          return (
            <div key={i} className="o8-cell">
              <span className="muted">第{i + 1}根 <span className="num">{b?.t ?? ["09:00", "09:05", "09:10"][i]}</span></span>
              <b className="num">{fmt(b?.close, 2)}</b>
              <span className={`num small ${dirClass(b?.vs_prev)}`}>{sfmt(b?.vs_prev ?? null, 2)}</span>
            </div>
          );
        })}
      </div>
      <p className="note">純記錄、不帶策略；自落地起每筆僅供盤後回顧</p>
    </Panel>
  );
}
