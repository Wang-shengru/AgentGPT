import { useCallback, useEffect, useRef, useState } from "react";
import {
  createChart,
  CrosshairMode,
  LineStyle,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import type { ChartPayload, KBar } from "../schema";
import { dirClass, fmt, sfmt } from "../format";
import { Panel } from "./ui";

const cssVar = (n: string) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const hhmm = (t: number) => {
  const d = new Date(t * 1000);
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
};
const mmdd = (t: number) => {
  const d = new Date(t * 1000);
  return `${String(d.getUTCMonth() + 1).padStart(2, "0")}/${String(d.getUTCDate()).padStart(2, "0")}`;
};
/** chart day window: D 08:45 -> D+1 05:01 (wall clock encoded as UTC) */
const windowOf = (date: string) => {
  const [y, m, d] = date.split("-").map(Number);
  const start = Date.UTC(y, m - 1, d, 8, 45) / 1000;
  return [start, start + (20 * 60 + 16) * 60] as const;
};

interface Props {
  theme: string;
  lastPrice: number | null;
  onBar: (fn: (b: KBar) => void) => () => void;
  paused: boolean;
  reconnects: number;
}

export function MainChart({ theme, lastPrice, onBar, paused, reconnects }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const svg = useRef<SVGSVGElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const candles = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const vols = useRef<ISeriesApi<"Histogram"> | null>(null);
  const pline = useRef<IPriceLine | null>(null);
  const bars = useRef<KBar[]>([]);
  const meta = useRef<ChartPayload>({});
  const [payload, setPayload] = useState<ChartPayload>({});
  const [hover, setHover] = useState<KBar | null>(null);
  const [count, setCount] = useState(0);
  const wantDate = useRef<string | null>(null);

  const colors = () => ({
    up: cssVar("--up"),
    down: cssVar("--down"),
    text: cssVar("--text"),
    muted: cssVar("--muted"),
    grid: cssVar("--grid"),
    bg: cssVar("--chart-bg"),
    hl: cssVar("--hl"),
  });

  const toCandle = (b: KBar) => {
    const c = colors();
    const col = b.c >= b.o ? c.up : c.down;
    return b.closed
      ? { time: b.t as UTCTimestamp, open: b.o, high: b.h, low: b.l, close: b.c, color: col, borderColor: col, wickColor: col }
      : { time: b.t as UTCTimestamp, open: b.o, high: b.h, low: b.l, close: b.c, color: "rgba(0,0,0,0)", borderColor: col, wickColor: col };
  };
  const toVol = (b: KBar) => {
    const c = colors();
    return { time: b.t as UTCTimestamp, value: b.v, color: (b.c >= b.o ? c.up : c.down) + (b.closed ? "99" : "55") };
  };

  // ---- overlay: night-session start, rollovers, forming bar dashed box
  const drawOverlay = useCallback(() => {
    const ch = chart.current, s = candles.current, el = svg.current;
    if (!ch || !s || !el) return;
    const ts = ch.timeScale();
    const h = el.clientHeight;
    const parts: string[] = [];
    const c = colors();
    const vline = (t: number, color: string, label: string, dash: string, ly = 14) => {
      const x = ts.timeToCoordinate(t as Time);
      if (x == null) return;
      parts.push(`<line x1="${x}" x2="${x}" y1="0" y2="${h - 28}" stroke="${color}" stroke-width="1.2" stroke-dasharray="${dash}"/>`);
      parts.push(`<text x="${x + 4}" y="${ly}" fill="${color}" font-size="11" font-family="var(--font-num)">${label}</text>`);
    };
    const m = meta.current;
    if (m.night_start) vline(m.night_start, c.hl, "夜盤 15:00", "6 3");
    (m.rollovers ?? []).forEach((r) => vline(r.t, c.hl, `轉倉 ${r.from}→${r.to}`, "2 3", 30));
    const last = bars.current[bars.current.length - 1];
    if (last && !last.closed) {
      const x = ts.timeToCoordinate(last.t as Time);
      const y1 = s.priceToCoordinate(last.h), y2 = s.priceToCoordinate(last.l);
      const spacing = ts.options().barSpacing;
      if (x != null && y1 != null && y2 != null) {
        const w = Math.max(6, spacing * 0.95);
        parts.push(
          `<rect x="${x - w / 2}" y="${y1 - 3}" width="${w}" height="${Math.max(6, y2 - y1 + 6)}" fill="none" stroke="${c.text}" stroke-width="1" stroke-dasharray="3 2" opacity=".85"/>`,
        );
      }
    }
    el.innerHTML = parts.join("");
  }, []);

  const raf = useRef(0);
  const redraw = useCallback(() => {
    cancelAnimationFrame(raf.current);
    raf.current = requestAnimationFrame(drawOverlay);
  }, [drawOverlay]);

  // ---- create chart once
  useEffect(() => {
    const el = box.current!;
    const ch = createChart(el, {
      autoSize: true,
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.06, bottom: 0.24 } },
      timeScale: {
        borderVisible: false,
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 4,
        barSpacing: 7,
        tickMarkFormatter: (t: Time) => hhmm(t as number),
      },
      localization: { timeFormatter: (t: Time) => `${mmdd(t as number)} ${hhmm(t as number)}`, locale: "zh-TW" },
      handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: true },
      handleScroll: { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: true },
    });
    const cs = ch.addCandlestickSeries({ priceLineVisible: false, lastValueVisible: false });
    const vs = ch.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
    ch.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    chart.current = ch;
    candles.current = cs;
    vols.current = vs;
    ch.timeScale().subscribeVisibleLogicalRangeChange(redraw);
    ch.subscribeCrosshairMove((p) => {
      if (!p.time) return setHover(null);
      setHover(bars.current.find((b) => b.t === p.time) ?? null);
    });
    const ro = new ResizeObserver(redraw);
    ro.observe(el);
    return () => {
      ro.disconnect();
      ch.remove();
      chart.current = null;
    };
  }, [redraw]);

  // ---- theme
  useEffect(() => {
    const ch = chart.current;
    if (!ch) return;
    const c = colors();
    ch.applyOptions({
      layout: { background: { color: c.bg }, textColor: c.muted, fontFamily: cssVar("--font-num") || "monospace" },
      grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
    });
    candles.current?.applyOptions({ upColor: c.up, downColor: c.down, borderUpColor: c.up, borderDownColor: c.down, wickUpColor: c.up, wickDownColor: c.down });
    if (bars.current.length) {
      candles.current?.setData(bars.current.map(toCandle));
      vols.current?.setData(bars.current.map(toVol));
    }
    pline.current?.applyOptions({ color: c.up });
    redraw();
  }, [theme, redraw]);

  // ---- data loading
  const load = useCallback(async (date: string | null, fit = true) => {
    wantDate.current = date;
    const res = await fetch(`/api/chart${date ? `?date=${date}` : ""}`);
    const p = (await res.json()) as ChartPayload;
    if (wantDate.current !== date) return;
    meta.current = p;
    bars.current = p.bars ?? [];
    setPayload(p);
    setCount(bars.current.length);
    candles.current?.setData(bars.current.map(toCandle));
    vols.current?.setData(bars.current.map(toVol));
    if (fit) chart.current?.timeScale().fitContent();
    redraw();
  }, [redraw]);

  useEffect(() => {
    load(null);
  }, [load]);

  // refetch after a reconnect (fills any gap) and on resume from pause
  useEffect(() => {
    if (reconnects > 1) load(meta.current.next ? meta.current.date ?? null : null, false);
  }, [reconnects, load]);
  useEffect(() => {
    if (!paused && meta.current.date) load(meta.current.next ? meta.current.date! : null, false);
  }, [paused, load]);

  // ---- live increments (only while showing the latest day)
  useEffect(
    () =>
      onBar((b) => {
        const m = meta.current;
        if (m.next || !m.date) return;
        const [, end] = windowOf(m.date);
        if (b.t >= end) {
          load(null);
          return;
        }
        const arr = bars.current;
        const last = arr[arr.length - 1];
        if (last && b.t < last.t) return;
        if (last && b.t > last.t && !last.closed) {
          last.closed = true;
          candles.current?.update(toCandle(last));
          vols.current?.update(toVol(last));
        }
        if (last && last.t === b.t) arr[arr.length - 1] = b;
        else arr.push(b);
        candles.current?.update(toCandle(b));
        vols.current?.update(toVol(b));
        setCount(arr.length);
        redraw();
      }),
    [onBar, load, redraw],
  );

  // ---- current-price dashed line
  useEffect(() => {
    const s = candles.current;
    if (!s) return;
    const show = lastPrice != null && !meta.current.next;
    if (!show) {
      if (pline.current) {
        s.removePriceLine(pline.current);
        pline.current = null;
      }
      return;
    }
    if (!pline.current)
      pline.current = s.createPriceLine({ price: lastPrice!, color: cssVar("--up"), lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "現價" });
    else pline.current.applyOptions({ price: lastPrice! });
  }, [lastPrice, payload]);

  // ---- interactions: double click -> today full session; ←/→ -> trading day
  useEffect(() => {
    const el = box.current!;
    const dbl = () => load(null, true);
    const key = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "SELECT" || tag === "INPUT") return;
      if (e.key === "ArrowLeft" && meta.current.prev) load(meta.current.prev);
      if (e.key === "ArrowRight" && meta.current.next) load(meta.current.next);
    };
    el.addEventListener("dblclick", dbl);
    window.addEventListener("keydown", key);
    return () => {
      el.removeEventListener("dblclick", dbl);
      window.removeEventListener("keydown", key);
    };
  }, [load]);

  const info = hover ?? bars.current[bars.current.length - 1] ?? null;
  const prevIdx = info ? bars.current.indexOf(info) - 1 : -1;
  const ref = prevIdx >= 0 ? bars.current[prevIdx].c : info?.o;
  const chg = info && ref != null ? info.c - ref : null;

  return (
    <Panel
      className="chart-panel"
      title={<>TXF 5分K｜日全盤｜純K｜無指標</>}
      right={
        <div className="chart-ctl">
          <button className="btn sm" disabled={!payload.prev} onClick={() => payload.prev && load(payload.prev)} aria-label="前一交易日">◀</button>
          <span className="num date">{payload.date ?? "—"}</span>
          <button className="btn sm" disabled={!payload.next} onClick={() => payload.next && load(payload.next)} aria-label="下一交易日">▶</button>
          <button className="btn sm" disabled={!payload.next} onClick={() => load(null)}>最新</button>
          <span className="muted num">K 棒數 {count}</span>
          <span className="tag store">8010・落地 tick</span>
        </div>
      }
    >
      <div className="chart-info num">
        {info ? (
          <>
            <span>{mmdd(info.t)} {hhmm(info.t)}</span>
            <span>開 {fmt(info.o)}</span>
            <span className="up">高 {fmt(info.h)}</span>
            <span className="down">低 {fmt(info.l)}</span>
            <span className={dirClass(chg)}>收 {fmt(info.c)}</span>
            <span className={dirClass(chg)}>漲跌 {sfmt(chg)}</span>
            <span>量 {fmt(info.v)}</span>
            {!info.closed && <span className="tag forming">形成中</span>}
          </>
        ) : (
          <span className="muted">無資料</span>
        )}
      </div>
      <div className="chart-box">
        <div ref={box} className="chart-canvas" />
        <svg ref={svg} className="chart-overlay" />
      </div>
      <p className="note">
        滾輪縮放（以游標為中心）・拖曳左右平移・雙擊回今日全盤・◀▶ 跳一個交易日｜日盤 08:45-13:45 → 夜盤 15:00-05:00，由落地 tick
        重建（8010）｜虛線框=形成中｜紅漲綠跌
      </p>
    </Panel>
  );
}
