import { useEffect, useState } from "react";
import { useFeed } from "./useFeed";
import { QuoteCards, TopBar } from "./components/Top";
import { OpeningEight, OrderFlow, PatternStrips, ThreeProducts } from "./components/Left";
import { MainChart } from "./components/Chart";
import { KeyLevels, TechCards } from "./components/Center";
import { MarketV3 } from "./components/Right";

function initialTheme(): string {
  const q = new URLSearchParams(location.search).get("theme");
  if (q) return q;
  try {
    return localStorage.getItem("twtx-theme") || "camo";
  } catch {
    return "camo";
  }
}

export default function App() {
  const [paused, setPaused] = useState(false);
  const [theme, setTheme] = useState(initialTheme);
  const feed = useFeed(paused);
  const snap = feed.snap;
  // apply synchronously: child effects (the chart) read CSS variables right after render
  if (document.documentElement.dataset.theme !== theme) document.documentElement.dataset.theme = theme;

  useEffect(() => {
    try {
      localStorage.setItem("twtx-theme", theme);
    } catch {
      /* private mode: ignore */
    }
  }, [theme]);

  const stale =
    !feed.connected ||
    (snap != null && (!snap.status.feed_connected || (snap.session.open && (snap.status.tick_age_s ?? 0) > 15)));

  return (
    <div className="app">
      <TopBar
        snap={snap}
        connected={feed.connected}
        lastMsgAt={feed.lastMsgAt}
        paused={paused}
        onPause={() => setPaused((p) => !p)}
        theme={theme}
        onTheme={setTheme}
      />
      <main className={`main ${stale ? "stale" : ""}`}>
        {stale && (
          <div className="delay-mask" role="status">
            <span>資料延遲</span>
            <small>{feed.connected ? "行情來源中斷，畫面保留最後數值，恢復後自動補齊" : "後端連線中斷，自動重連中…"}</small>
          </div>
        )}
        {paused && <div className="paused-flag">已暫停・背景持續收資料</div>}
        <QuoteCards snap={snap} />
        <div className="cols">
          <div className="col left">
            <OrderFlow snap={snap} />
            <ThreeProducts snap={snap} />
            <PatternStrips snap={snap} />
            <OpeningEight o={snap?.opening8} />
          </div>
          <div className="col center">
            <div className="chart-row">
              <MainChart
                theme={theme}
                lastPrice={snap?.quotes.txf.price ?? null}
                onBar={feed.onBar}
                paused={paused}
                reconnects={feed.reconnects}
              />
              <KeyLevels levels={snap?.levels ?? []} />
            </div>
            <TechCards snap={snap} />
          </div>
          <div className="col right">
            <MarketV3 snap={snap} />
          </div>
        </div>
      </main>
      <footer className="disclaimer">本系統僅供行情觀察與研究紀錄，不構成任何投資建議。</footer>
    </div>
  );
}
