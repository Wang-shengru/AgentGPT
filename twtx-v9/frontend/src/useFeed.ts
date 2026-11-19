import { useEffect, useRef, useState } from "react";
import type { KBar, Snapshot, WsMessage } from "./schema";

export interface FeedState {
  snap: Snapshot | null;
  connected: boolean;
  lastMsgAt: number; // performance.now() of last snapshot
  reconnects: number;
}

type BarListener = (b: KBar) => void;

/**
 * Single WebSocket to the backend. Keeps receiving while paused; the paused flag only freezes
 * what is handed to React (and K-bar listeners). Reconnects with backoff.
 */
export function useFeed(paused: boolean) {
  const [state, setState] = useState<FeedState>({ snap: null, connected: false, lastMsgAt: 0, reconnects: 0 });
  const latest = useRef<Snapshot | null>(null);
  const pausedRef = useRef(paused);
  const barListeners = useRef(new Set<BarListener>());
  const pendingBars = useRef<KBar[]>([]);
  const lastAt = useRef(0);

  useEffect(() => {
    pausedRef.current = paused;
    if (!paused) {
      // resume: apply what arrived while frozen
      if (latest.current) setState((s) => ({ ...s, snap: latest.current, lastMsgAt: lastAt.current }));
      const bars = pendingBars.current;
      pendingBars.current = [];
      bars.forEach((b) => barListeners.current.forEach((fn) => fn(b)));
    }
  }, [paused]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let timer: number | undefined;
    let retry = 0;
    let closed = false;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => {
        retry = 0;
        setState((s) => ({ ...s, connected: true, reconnects: s.reconnects + 1 }));
      };
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data) as WsMessage;
        if (msg.type === "snapshot") {
          latest.current = msg.data;
          lastAt.current = performance.now();
          if (!pausedRef.current) setState((s) => ({ ...s, snap: msg.data, lastMsgAt: lastAt.current }));
        } else if (msg.type === "kbar") {
          if (pausedRef.current) {
            const q = pendingBars.current;
            if (q.length && q[q.length - 1].t === msg.data.t) q[q.length - 1] = msg.data;
            else q.push(msg.data);
          } else barListeners.current.forEach((fn) => fn(msg.data));
        }
      };
      ws.onclose = () => {
        setState((s) => ({ ...s, connected: false }));
        if (closed) return;
        retry = Math.min(retry + 1, 6);
        timer = window.setTimeout(connect, 500 * 2 ** retry);
      };
      ws.onerror = () => ws?.close();
    };
    connect();
    const ping = window.setInterval(() => ws?.readyState === 1 && ws.send("ping"), 15000);
    return () => {
      closed = true;
      window.clearTimeout(timer);
      window.clearInterval(ping);
      ws?.close();
    };
  }, []);

  const onBar = (fn: BarListener) => {
    barListeners.current.add(fn);
    return () => barListeners.current.delete(fn);
  };

  return { ...state, onBar };
}
