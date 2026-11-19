import { useEffect, useState } from "react";
import type { Snapshot } from "../schema";
import { dirClass, fmt, hms, isNum, sfmt } from "../format";

type Lv = "ok" | "warn" | "bad" | "info";

function Pill({ lv, children, title }: { lv: Lv; children: React.ReactNode; title?: string }) {
  return (
    <span className={`pill ${lv}`} title={title}>
      <i className="dot" />
      {children}
    </span>
  );
}

export const THEMES = [
  { key: "camo", name: "暗色迷彩" },
  { key: "comic", name: "英雄漫畫" },
];

export function TopBar(props: {
  snap: Snapshot | null;
  connected: boolean;
  lastMsgAt: number;
  paused: boolean;
  onPause: () => void;
  theme: string;
  onTheme: (t: string) => void;
}) {
  const { snap, connected } = props;
  const [, tick] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => tick((x) => x + 1), 250);
    return () => window.clearInterval(id);
  }, []);
  const age = props.lastMsgAt ? (performance.now() - props.lastMsgAt) / 1000 : null;
  const st = snap?.status;
  const sess = snap?.session;
  // countdown keeps ticking locally between snapshots
  const cd = sess ? Math.max(0, sess.countdown_s - (age ?? 0)) : 0;
  const tickAge = st?.tick_age_s != null ? st.tick_age_s + (age ?? 0) : null;
  const lvAge: Lv = !connected ? "bad" : age == null ? "warn" : age < 2.5 ? "ok" : age < 6 ? "warn" : "bad";
  const lag = st?.driver_lag_s ?? null;
  const lvLag: Lv = !connected || lag == null ? "bad" : lag < 1 ? "ok" : lag < 3 ? "warn" : "bad";
  const lvTick: Lv = !connected || !st?.feed_connected
    ? "bad"
    : !sess?.open
      ? "warn"
      : tickAge == null ? "warn" : tickAge < 5 ? "ok" : tickAge < 15 ? "warn" : "bad";
  const clock = snap ? snap.ts.slice(11, 19) : "--:--:--";
  return (
    <header className="topbar">
      <div className="brand">
        <div className="logo">TWTX V9 TERMINAL</div>
        <div className="tagline">唯讀・無策略・無部位</div>
      </div>
      <div className="pills">
        <Pill lv={sess?.open ? "ok" : "warn"}>
          {sess?.label ?? "—"} {sess?.countdown_label ?? "收盤倒數"} <b className="num">{hms(cd)}</b>
        </Pill>
        <Pill lv={lvAge} title="主服務 API/WS（距上次快照秒數）">
          {st?.api.port ?? 8001}・<b className="num">{age == null ? "—" : `${Math.floor(age)}s`}</b>
        </Pill>
        <Pill lv={lvLag} title="驅動＝tick 入列到計算完成的延遲">
          驅動 <b className="num">{lag == null ? "—" : `${Math.floor(lag)}s`}</b>
        </Pill>
        <Pill lv={lvTick} title={`距上次收到 tick 秒數｜feed: ${st?.feed_text ?? "—"}`}>
          行情 <b className="num">{tickAge == null ? "—" : `${Math.floor(tickAge)}s`}</b>
        </Pill>
        <Pill lv="info" title="描述性盤態（非訊號）">{st?.regime ?? "—"}</Pill>
        <Pill lv={!connected ? "bad" : st?.engine.ok ? "ok" : "bad"} title="資料引擎健康狀態">
          {st?.engine.port ?? 8006}
        </Pill>
        <Pill
          lv={!connected ? "bad" : st?.store.ok ? (st.store.pending > 5000 ? "warn" : "ok") : "bad"}
          title={`落地 tick 寫入：${fmt(st?.store.rows)} 筆，待寫 ${fmt(st?.store.pending)}`}
        >
          {st?.store.port ?? 8010} 5K
        </Pill>
        {snap?.mode === "mock" && <Pill lv="info" title="未設定 API Key：模擬行情">MOCK</Pill>}
      </div>
      <div className="top-right">
        <div className="clock num" aria-label="盤面時間">{clock}</div>
        <button className={`btn ${props.paused ? "active" : ""}`} onClick={props.onPause} title="凍結畫面更新，背景持續收資料">
          {props.paused ? "繼續" : "暫停"}
        </button>
        <select className="theme-select" value={props.theme} onChange={(e) => props.onTheme(e.target.value)} aria-label="主題">
          {THEMES.map((t) => (
            <option key={t.key} value={t.key}>{t.name}</option>
          ))}
        </select>
      </div>
    </header>
  );
}

function Chg({ c, p }: { c: number | null; p?: number | null }) {
  return (
    <span className={`chg num ${dirClass(c)}`}>
      {sfmt(c)}
      {p !== undefined && <span className="pct"> {sfmt(p, 2, "%")}</span>}
    </span>
  );
}

function Card(props: { title: React.ReactNode; tag?: React.ReactNode; className?: string; children: React.ReactNode }) {
  return (
    <div className={`qcard ${props.className ?? ""}`}>
      <div className="qcard-head">
        <span>{props.title}</span>
        {props.tag}
      </div>
      <div className="qcard-body">{props.children}</div>
    </div>
  );
}

export function QuoteCards({ snap }: { snap: Snapshot | null }) {
  const q = snap?.quotes;
  const t = q?.txf;
  const pos = t?.range_pos;
  return (
    <div className="quotes">
      <Card
        className="wide"
        title={<>TXF 台指近月 <span className="code num">{t?.code ?? ""}</span></>}
        tag={<span className={`live ${snap?.session.open ? "on" : ""}`}>LIVE</span>}
      >
        <div className="txf-main">
          <div className={`big num ${dirClass(t?.change)}`}>{fmt(t?.price)}</div>
          <Chg c={t?.change ?? null} p={t?.change_pct ?? null} />
        </div>
        <div className="kv num">
          <span>開 {fmt(t?.open)}</span>
          <span>振幅 {fmt(t?.amplitude)}{isNum(t?.amplitude_pct) ? ` (${t!.amplitude_pct!.toFixed(2)}%)` : ""}</span>
          <span>區間 {isNum(pos) ? `${pos!.toFixed(0)}%` : "—"}</span>
        </div>
        <div className="range">
          <span className="num down">{fmt(t?.low)}</span>
          <div className="range-bar">
            <div className="range-fill" style={{ width: `${isNum(pos) ? pos : 50}%` }} />
            <div className="range-mark" style={{ left: `${isNum(pos) ? pos : 50}%` }} />
          </div>
          <span className="num up">{fmt(t?.high)}</span>
        </div>
      </Card>
      {(["mxf", "tmf"] as const).map((k) => (
        <Card key={k} title={<>{k === "mxf" ? "MXF 小台" : "TMF 微台"} <span className="code num">{q?.[k].code ?? ""}</span></>}>
          <div className={`mid num ${dirClass(q?.[k].change)}`}>{fmt(q?.[k].price)}</div>
          <Chg c={q?.[k].change ?? null} p={q?.[k].change_pct ?? null} />
        </Card>
      ))}
      <Card title="基差" tag={q?.basis.label ? <span className={`tag ${q.basis.basis! > 0 ? "up" : "down"}`}>{q.basis.label}</span> : null}>
        <div className={`mid num ${dirClass(q?.basis.basis)}`}>{sfmt(q?.basis.basis, 1)}</div>
        <div className="kv num">
          <span>現貨 {fmt(q?.basis.spot, 2)}</span>
          <span>成交 {fmt(q?.basis.spot_amount_e8, 0)} 億</span>
        </div>
      </Card>
      <Card title="VWAP 均價">
        <div className="mid num">{fmt(q?.vwap.vwap, 1)}</div>
        <div className={`num ${dirClass(q?.vwap.dev_pct)}`} title={`自算 ${fmt(q?.vwap.self_vwap, 2)}｜差 ${fmt(q?.vwap.check_diff, 3)}`}>
          偏離 {sfmt(q?.vwap.dev_pct, 2, "%")}
        </div>
      </Card>
      <Card title="成交量（口）">
        <div className="mid num">{fmt(q?.volume.total)}</div>
        <div className={`num ${isNum(q?.volume.ratio5) && q!.volume.ratio5! >= 1.5 ? "hl" : ""}`}>
          5 分量比 {isNum(q?.volume.ratio5) ? q!.volume.ratio5!.toFixed(2) : "—"}
        </div>
      </Card>
      <Card title={<>次月 <span className="code num">{q?.next.code ?? ""}</span></>}>
        <div className={`mid num ${dirClass(q?.next.change)}`}>{fmt(q?.next.price)}</div>
        <div className="kv num">
          <span className={dirClass(q?.next.spread)}>價差 {sfmt(q?.next.spread)}</span>
          <span>量 {fmt(q?.next.volume)}</span>
        </div>
      </Card>
      <Card title="盤面 V3 一致度">
        <div className={`mid ${q?.v3.verdict.includes("多") ? "up" : q?.v3.verdict.includes("空") ? "down" : "flat"}`}>
          {q?.v3.verdict ?? "—"}
        </div>
        <div className="kv num">
          <span>淨值 {sfmt(q?.v3.net, 2)} / ±4</span>
          <span>可用 {q?.v3.n_available ?? 0}/{q?.v3.n_items ?? 13}</span>
        </div>
      </Card>
    </div>
  );
}
