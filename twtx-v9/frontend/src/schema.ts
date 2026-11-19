// WebSocket / REST JSON schema. MUST stay identical to backend/twtx/schema.py
// (enforced by backend/tests/test_schema.py, which compares interface fields one-to-one).

export interface SessionStatus {
  kind: string | null;
  label: string;
  key: string;
  trading_date: string;
  countdown_label: string;
  countdown_s: number;
  open: boolean;
}

export interface ServiceHealth {
  port: number;
  ok: boolean;
}

export interface StoreHealth {
  port: number;
  ok: boolean;
  rows: number;
  pending: number;
}

export interface Status {
  feed_connected: boolean;
  feed_text: string;
  tick_age_s: number | null;
  driver_lag_s: number | null;
  calc_ms: number;
  api: ServiceHealth;
  engine: ServiceHealth;
  store: StoreHealth;
  regime: string;
  queue: number;
}

export interface QuoteCard {
  code: string | null;
  price: number | null;
  change: number | null;
  change_pct: number | null;
  volume: number;
  ref: number | null;
}

export interface TxfCard extends QuoteCard {
  open: number | null;
  high: number | null;
  low: number | null;
  range_pos: number | null;
  amplitude: number | null;
  amplitude_pct: number | null;
}

export interface NextCard extends QuoteCard {
  spread: number | null;
}

export interface BasisCard {
  basis: number | null;
  label: string | null;
  spot: number | null;
  spot_ref: number | null;
  spot_amount_e8: number | null;
  underlying: number | null;
}

export interface VwapCard {
  vwap: number | null;
  dev_pct: number | null;
  self_vwap: number | null;
  check_diff: number | null;
}

export interface VolumeCard {
  total: number;
  ratio5: number | null;
  bar_volume: number | null;
}

export interface V3Card {
  verdict: string;
  net: number;
  n_available: number;
  n_items: number;
}

export interface Quotes {
  txf: TxfCard;
  mxf: QuoteCard;
  tmf: QuoteCard;
  next: NextCard;
  basis: BasisCard;
  vwap: VwapCard;
  volume: VolumeCard;
  v3: V3Card;
}

export interface FlowProduct {
  session: string;
  tx_delta: number;
  tx_buy: number;
  tx_sell: number;
  vo_delta: number;
  vo_buy: number;
  vo_sell: number;
  io_delta: number | null;
  bid_total: number | null;
  ask_total: number | null;
  buy_ratio: number | null;
  buy_ratio_exchange: number | null;
  scale_tx: number;
  scale_vo: number;
  scale_io: number;
  scale_ratio: number;
  session_volume: number;
  ewma_delta: number;
}

export interface Flow {
  badge: string;
  txf: FlowProduct;
  mxf: FlowProduct;
  tmf: FlowProduct;
}

export interface MaRow {
  n: number;
  value: number | null;
  slope: number | null;
}

export interface Boll {
  upper: number;
  mid: number;
  lower: number;
  width: number;
  pct_b: number;
  prev_width: number | null;
}

export interface Macd {
  dif: number;
  dea: number;
  osc: number;
  osc_prev: number;
}

export interface Tech {
  ma5: MaRow[];
  ma5_label: string;
  ma60: MaRow[];
  ma60_close: number | null;
  ma60_label: string;
  boll: Boll | null;
  macd: Macd | null;
}

export interface Level {
  key: string;
  label: string;
  price: number;
  dist: number | null;
}

export interface PatternCell {
  t: string;
  color: "up" | "down" | "doji";
  pattern: string | null;
  bias: number;
  body_ratio: number;
}

export interface PatternHit {
  tf: string;
  t: string;
  pattern: string;
}

export interface Patterns {
  k5: PatternCell[];
  k60: PatternCell[];
  kS: PatternCell[];
  latest: PatternHit | null;
}

export interface Opening8Bar {
  t: string;
  close: number | null;
  vs_prev: number | null;
}

export interface Opening8 {
  available?: boolean;
  key?: string | null;
  name?: string;
  tendency?: string;
  desc?: string;
  date?: string;
  prev_close?: number | null;
  bars?: Opening8Bar[];
}

export interface V3Item {
  key: string;
  group: string;
  label: string;
  direction: number;
  strength: number;
  value: number | null;
  display: string;
  text: string;
  voting: boolean;
  available: boolean;
}

export interface V3Group {
  key: string;
  name: string;
  score: number;
  available: boolean;
  n_voting: number;
  n_available: number;
  items: V3Item[];
}

export interface V3 {
  net: number;
  verdict: string;
  sentence: string;
  consistency: number;
  bull: number;
  bear: number;
  neutral: number;
  n_available: number;
  n_items: number;
  groups_available: number;
  n_groups: number;
  groups: V3Group[];
}

export interface Snapshot {
  ts: string;
  mode: string;
  session: SessionStatus;
  status: Status;
  quotes: Quotes;
  flow: Flow;
  tech: Tech;
  levels: Level[];
  patterns: Patterns;
  opening8: Opening8;
  v3: V3;
}

export interface KBar {
  t: number; // Taipei wall clock encoded as UTC epoch seconds
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
  closed: boolean;
  code: string;
}

export interface Rollover {
  t: number;
  from: string;
  to: string;
}

export interface ChartPayload {
  date?: string | null;
  dates?: string[];
  prev?: string | null;
  next?: string | null;
  bars?: KBar[];
  night_start?: number | null;
  rollovers?: Rollover[];
}

export interface SnapshotMsg {
  type: "snapshot";
  data: Snapshot;
}

export interface KBarMsg {
  type: "kbar";
  data: KBar;
}

export type WsMessage = SnapshotMsg | KBarMsg;
