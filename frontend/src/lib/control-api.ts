/**
 * Client for the desktop control plane (`backend/routers/control.py`).
 *
 * Three things make this its own module rather than more of `lib/api.ts`:
 *
 * 1. **Origin.** In the packaged desktop app FastAPI serves the exported
 *    frontend itself, on a port the shell picks at launch, so every request is
 *    SAME-ORIGIN. `lib/api.ts`'s absolute `http://localhost:8000` would point at
 *    the wrong process. `AEGIS_DESKTOP_BUILD=1` sets the compile-time flag below.
 * 2. **404 is a state, not a crash.** Some control endpoints are being written
 *    concurrently with these pages. A missing endpoint must render "not built
 *    yet", never take a page down — so the error carries its status.
 * 3. **No invented fields.** The endpoints that already exist are typed from the
 *    router. The ones that do not exist yet are read through the tolerant
 *    helpers at the bottom, which return `null` when a key is absent so the UI
 *    can print an em dash instead of a number nobody measured.
 */

import { API_BASE } from "./api";

/** Same origin inside the packaged app; the dev backend otherwise. One
 *  resolver for both clients (`api.ts`), so a placeholder in the build env is
 *  refused the same way here (2026-10-06). */
export const CONTROL_BASE = API_BASE;

export class ControlError extends Error {
  readonly status: number;
  readonly detail: string;
  constructor(status: number, detail: string) {
    super(detail || `control API error ${status}`);
    this.name = "ControlError";
    this.status = status;
    this.detail = detail;
  }
}

/** A 404 means the endpoint has not landed yet, not that the app is broken. */
export function isNotBuilt(e: unknown): boolean {
  return e instanceof ControlError && e.status === 404;
}
/** 403 = mutating routes are off because AEGIS_CONTROL_ENABLED is not 1. */
export function isForbidden(e: unknown): boolean {
  return e instanceof ControlError && e.status === 403;
}
/** status 0 = the request never reached a server at all. */
export function isUnreachable(e: unknown): boolean {
  return e instanceof ControlError && e.status === 0;
}

export function errorText(e: unknown): string {
  if (e instanceof ControlError) return `${e.status || "no response"} — ${e.detail}`;
  return e instanceof Error ? e.message : String(e);
}

async function controlFetch<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = 20_000,
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${CONTROL_BASE}/api/control${path}`, {
      ...init,
      signal: init?.signal ?? AbortSignal.timeout(timeoutMs),
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch (e) {
    throw new ControlError(
      0,
      e instanceof Error && e.name === "TimeoutError"
        ? `no answer from the backend within ${Math.round(timeoutMs / 1000)}s`
        : "cannot reach the backend",
    );
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
      else if (body?.detail) detail = JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body: keep the status line */
    }
    throw new ControlError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function post<T>(path: string, body?: unknown, timeoutMs?: number): Promise<T> {
  return controlFetch<T>(
    path,
    { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) },
    timeoutMs,
  );
}

// ---------------------------------------------------------------- shapes
// These mirror `backend/routers/control.py` exactly. Do not add a field here
// that the router does not return.

export interface ControlRun {
  pid: number;
  job: string;
  argv?: string[];
  log?: string;
  started_utc?: string;
  alive?: boolean;
  log_size_bytes?: number;
  log_mtime_utc?: string | null;
}

export interface LocalGgufProbe {
  url: string;
  reachable: boolean;
  detail: string;
}

export interface ServicesResponse {
  utc: string;
  control_enabled: boolean;
  backend: { pid: number; cwd: string };
  local_gguf: LocalGgufProbe;
  night_dir: string;
  stop_file_present: boolean;
  runs: ControlRun[];
  jobs_available: string[];
}

export interface JobsResponse {
  utc: string;
  queue: string[];
  extra: string[];
  whitelist: string[];
}

export interface RunLogResponse {
  pid: number;
  job: string | null;
  alive: boolean;
  log: string | null;
  tail: string;
}

export interface LeaderboardResponse {
  utc: string;
  path: string;
  markdown: string | null;
  receipts: string[];
}

export interface BalancesResponse {
  utc: string;
  deepseek_balance_last_reading: Record<string, unknown> | null;
  source: string;
  note: string;
}

export interface StartedRun {
  started: boolean;
  pid: number;
  job: string;
  argv: string[];
  log: string;
  started_utc: string;
}

export interface StopResponse {
  pid: number;
  stop_file: string;
  killed: boolean;
  alive: boolean;
  detail: string;
  utc: string;
}

/** Endpoints still being written: shape unknown, so nothing is typed shut. */
export type UnknownPayload = Record<string, unknown>;

/**
 * `GET /api/control/llama` — `backend.services.llama_server.status()`.
 *
 * Two fields carry the whole meaning of the page and neither is a synonym of
 * "up": `listening` is the port being bound, `ready` is `/health` returning 200.
 * A multi-GB model binds the port instantly and answers minutes later, so
 * `listening && !ready` is LOADING and must never render as running.
 *
 * `foreign` is `listening && !started_by_aegis` — something is serving that
 * Aegis did not start, and stopping it is a different act (see `stopLlama`).
 */
export interface LlamaVram {
  used_mib?: number;
  total_mib?: number;
  gpu?: string;
}
export interface LlamaStatus {
  url: string;
  listening: boolean;
  ready: boolean;
  pid: number | null;
  started_by_aegis: boolean;
  foreign: boolean;
  model: string | null;
  model_present: boolean;
  binary_present: boolean;
  started_utc: string | null;
  vram: LlamaVram | null;
  detail: string;
  utc?: string;
  model_path?: string;
  binary_path?: string;
  n_cpu_moe?: number;
}

/**
 * `POST /api/control/llama/stop` — a refusal is a normal 200 body.
 *
 * A foreign server comes back `{ok:false, needs_confirmation:true, detail}`
 * rather than an error, because it is a question, not a failure.
 */
export interface LlamaActionResponse {
  ok?: boolean;
  action?: string;
  reason?: string;
  detail?: string;
  needs_confirmation?: boolean;
  pid?: number;
  note?: string;
  escalated_to_force?: boolean;
  waited_s?: number;
  exit_code?: number;
  status?: LlamaStatus;
  [k: string]: unknown;
}


/**
 * `GET /api/control/sim` — the simulation's DERIVED state.
 *
 * `UNCLEAN` is not stored, it is inferred from a stale heartbeat or a dead pid:
 * a crashed process cannot set its own "I crashed" flag, and a status that
 * waits to be told reports RUNNING forever. It means the checkpoint is good and
 * the cycle after it is unknown — different facts from "it finished".
 */
export type SimState =
  | "IDLE" | "RUNNING" | "STOPPING" | "STOPPED" | "COMPLETED" | "UNCLEAN";

export interface SimSession {
  id?: string;
  kind?: string;
  mode?: string;
  state?: SimState;
  started?: string;
  planned_end?: string;
  cycle?: number;
  resume_count?: number;
  unclean_reason?: string;
  end_reason?: string;
  checkpoint?: { cycle?: number; at?: string } | null;
  cycles?: Array<{ cycle: number; at: string; elapsed_s?: number; errors?: unknown[] }>;
  [k: string]: unknown;
}

export interface SimStatus {
  state: SimState;
  session: SimSession | null;
  pid_alive?: boolean;
  heartbeat_age_s?: number | null;
  remaining_s?: number | null;
  cycle?: number;
  resumable?: boolean;
  stop_requested?: boolean;
  allowed_hours: number[];
  smoke_minutes: number[];
}

/** A refusal is a normal 200 body — a duration outside the declared set, or a
 * session already running. The sentence is the point, so it is shown verbatim. */
export interface SimStartResponse {
  ok: boolean;
  session?: SimSession;
  refused?: string;
}

export interface SimStopResponse {
  ok: boolean;
  state?: string;
  cycle?: number;
  detail?: string;
}

/** `GET /api/control/sim/preflight` — every dependency an 8-hour run needs,
 * MEASURED (a real broker call, a real completion), not read from config. */
export interface SimPreflight {
  green: boolean;
  red: string[];
  rows: Record<string, Record<string, unknown>>;
  at?: string;
}

/** `POST /api/control/ask`. Two disjoint shapes: an answer, or a refusal. */
export interface AskResponse {
  ok?: boolean;
  utc?: string;
  question?: string;
  answer?: string | null;
  backend?: string;
  model?: string | null;
  context_sources?: string[];
  context_truncated?: boolean;
  authority?: string;
  cost_usd?: number;
  /** present only when the local model is not ready; names the fix */
  refusal?: string;
  /** true when THIS request started the model server (only ever with start=true) */
  started?: boolean;
  /** wall-clock seconds spent waiting for the model to answer /health */
  waited_s?: number;
  start_result?: Record<string, unknown> | null;
  llama?: LlamaStatus;
  /** Which read tool the DETERMINISTIC router picked, and why (O6). The model
   *  does not choose its tools, so this is auditable: the same question always
   *  retrieves the same receipts. */
  tool?: string;
  tool_arg?: string | null;
  routed_because?: string;
  tools_available?: string[];
  /** "ledger" when the answer came from the morning's forecast rows with no
   *  model in the path at all; "local_model" otherwise. */
  answered_by?: string;
  morning_has_run?: boolean;
  n_forecast_rows?: number;
  [k: string]: unknown;
}

/**
 * `GET /api/control/fleet` — being added in the same session as these pages.
 *
 * `estimable` is the field that matters: where it is false the row carries no
 * usable t-stat and the page must print `why_not_estimable`, not a number.
 */
export interface FleetLane {
  lane?: string;
  nav?: number;
  since_inception_pct?: number;
  excess_vs_benchmark_pct?: number;
  mean_daily_excess_pct?: number;
  se_daily_excess_pct?: number;
  t_stat?: number;
  n_days?: number;
  estimable?: boolean;
  why_not_estimable?: string;
  [k: string]: unknown;
}
export interface FleetResponse {
  utc?: string;
  inception_date?: string;
  age_days?: number;
  benchmark?: { symbol?: string; total_return_pct?: number; n_days?: number };
  lanes?: FleetLane[];
  aggregate?: FleetLane;
  note?: string;
  [k: string]: unknown;
}

// ----------------------------------------------------------------- reads

export const getServices = () => controlFetch<ServicesResponse>("/services");
export const getJobs = () => controlFetch<JobsResponse>("/jobs");
export const getLeaderboard = () => controlFetch<LeaderboardResponse>("/leaderboard");
export const getBalances = () => controlFetch<BalancesResponse>("/balances");
export const getRunLog = (pid: number, tail = 20_000) =>
  controlFetch<RunLogResponse>(`/runs/${pid}/log?tail=${tail}`);

/** Being added concurrently. 404 => "not built yet", never a thrown page. */
export const getLlama = () => controlFetch<LlamaStatus>("/llama");
export const getSim = () => controlFetch<SimStatus>("/sim");
export const getSimPreflight = () => controlFetch<SimPreflight>("/sim/preflight");
/** Not in the router yet either; the Fleet page renders "not available" on 404. */
export const getFleet = () => controlFetch<FleetResponse>("/fleet");
/** Lane B: every paper book WITH its twins. Never one without the other. */
export const getBooks = () => controlFetch<BooksResponse>("/books");

// ---------------------------------------------------------------- writes

export const runJob = (job: string, hours?: number) =>
  post<StartedRun>(
    `/run/${encodeURIComponent(job)}${hours != null ? `?hours=${hours}` : ""}`,
  );
export const runNight = (hours: number) => post<StartedRun>(`/night?hours=${hours}`);

/** Start a session. `hours` must be one of `allowed_hours`; `minutes` runs a
 * named smoke rehearsal. A refusal comes back as `{ok:false, refused}`. */
export const startSim = (opts: { hours?: number; minutes?: number; resume?: boolean }) => {
  const q = new URLSearchParams();
  if (opts.hours != null) q.set("hours", String(opts.hours));
  if (opts.minutes != null) q.set("minutes", String(opts.minutes));
  if (opts.resume) q.set("resume", "true");
  return post<SimStartResponse>(`/sim/start?${q.toString()}`);
};

/** Ask for a SAFE stop. There is deliberately no force: the loop ends at a unit
 * boundary, after the current cycle has checkpointed. */
export const stopSim = () => post<SimStopResponse>("/sim/stop");
export const stopPid = (pid: number, forceAfterS = 0) =>
  post<StopResponse>(`/stop/${pid}?force_after_s=${forceAfterS}`, undefined, 150_000);
export const clearStopFile = () =>
  post<{ cleared: boolean; utc: string }>("/stop-file/clear");

/** A cold start loads several GB from disk; `wait_s` is capped at 600 server-side. */
export const startLlama = () =>
  post<LlamaActionResponse>("/llama/start", undefined, 120_000);

/**
 * Stop the local model server.
 *
 * `allowForeign` is a CONSENT gate, not a retry flag. Without it a server Aegis
 * did not start comes back `{ok:false, needs_confirmation:true, detail}` — a 200
 * with a question in it. The caller must show that `detail` to the user and only
 * then call again with `true`; nothing here escalates on its own.
 */
export const stopLlama = (allowForeign = false) =>
  post<LlamaActionResponse>(
    `/llama/stop${allowForeign ? "?allow_foreign=true" : ""}`,
    undefined,
    60_000,
  );

/**
 * Ask the built-in local model about the receipts.
 *
 * The router declares `question: str` as a plain parameter, which FastAPI binds
 * from the QUERY STRING, not the body. The JSON-body retry stays behind it: if
 * the endpoint ever moves to a body model, one retry finds it rather than
 * showing the user a 422 they cannot act on.
 */
export async function ask(
  question: string,
  opts: { start?: boolean } = {},
): Promise<AskResponse> {
  // `start=true` is only ever sent from an explicit button press: starting a
  // multi-GB model server is a decision about the machine's VRAM, and the
  // endpoint never takes it on its own. The wait is long because a cold load
  // is, so the timeout has to outlast it.
  const startQ = opts.start ? "&start=true" : "";
  const timeout = opts.start ? 300_000 : 180_000;
  try {
    return await post<AskResponse>(
      `/ask?question=${encodeURIComponent(question)}${startQ}`,
      undefined,
      timeout,
    );
  } catch (e) {
    if (e instanceof ControlError && e.status === 422) {
      return await post<AskResponse>(
        "/ask",
        opts.start ? { question, start: true } : { question },
        timeout,
      );
    }
    throw e;
  }
}

// ------------------------------------------------------- the board (O4 / O8)
// Five read-only GETs. Every shape below mirrors `backend/routers/control.py`
// field for field; nothing is added here that the router does not return.

export interface UniverseRow {
  symbol: string;
  sector: string | null;
  exchange: string | null;
  verdict: string | null;
  tracker_status: string | null;
  upside: number | null;
  ratio: number | null;
  consensus_tracker: number | null;
  consensus_scale: string;
  n_analysts: number | null;
  coverage: number | null;
  p_beat: number | null;
  learner_score: number | null;
  median_dollar_volume: number | null;
  execution_tier: string | null;
  market_cap_usd: number | null;
  ret_12m: number | null;
  analyst_snapshot: {
    observed_at?: string | null;
    target_mean?: number | null;
    consensus_rating?: number | null;
    consensus_label?: string | null;
    n_analysts?: number | null;
    scale: string;
    source: string;
  } | null;
  books: string[];
  last_event: string | null;
  last_review: { sentence: string; receipt: string } | null;
}

export interface UniverseResponse {
  utc: string;
  available: boolean;
  error?: string;
  /** The file the rows came from. Printed on the page beside the count. */
  universe_source: string | null;
  universe_day?: string;
  /** Rows IN THE FILE. Must equal what the header prints as the denominator. */
  universe_rows: number;
  n_matched: number;
  rows_shown: number;
  offset: number;
  limit: number;
  q: string | null;
  sort: { key: string; dir: string; missing_values: string };
  sorts: string[];
  vintage?: UnknownPayload;
  tracker_vintage?: UnknownPayload;
  joins?: UnknownPayload;
  rows: UniverseRow[];
}

export interface TreeFile {
  path: string;
  name: string;
  bytes: number;
  too_big: boolean;
}

export interface TreeResponse {
  utc: string;
  root: string;
  path: string;
  exists: boolean;
  roots: string[];
  n_files: number;
  files: TreeFile[];
  max_bytes: number;
  note?: string;
}

export interface FileResponse {
  utc: string;
  path: string;
  abs: string;
  bytes: number;
  lines: number;
  text: string;
  root: string | null;
  commits: string[];
  /** Null when git ran and found commits; a reason otherwise. Never omitted. */
  git_note: string | null;
}

export interface AppLogResponse {
  utc: string;
  path: string;
  exists: boolean;
  lines: string[];
  bytes?: number;
  n_lines_total?: number;
  tail?: number;
  note?: string;
  error?: string;
}

// ------------------------------------------------------------------ books
//
// Lane B. The one thing this type says that a comment could not: `twins` is
// NOT optional. A book's number is never rendered without its control's (B3),
// and the payload has no shape in which it could be -- so neither does the
// type, and a page that forgets to render them will not compile its way past
// a missing field.

export interface BookTwin {
  book_id: string;
  kind: string | null;
  construction: string | null;
  present: boolean;
  nav: number | null;
  last_mark: string | null;
  n_marks: number;
  since_inception_pct: number | null;
  why_no_nav?: string;
}

export interface BookForecasts {
  n_open: number;
  n_graded?: number;
  n_engine_graded?: number;
  n_base_rate_graded?: number;
  last_grade: string | null;
  brier: number | null;
  base_rate_brier: number | null;
  reading?: string;
  why?: string;
  error?: string;
}

export interface BookWorstCase {
  n_names?: number;
  gross_over_equity?: number | null;
  gross_cap_declared?: number | null;
  stop_pct?: number | null;
  worst_case_usd?: number | null;
  worst_case_pct_of_equity?: number | null;
  verdict?: string;
  error?: string;
}

export interface BookRow {
  book_id: string;
  fingerprint: string;
  strategy_id: string;
  title: string;
  cadence: string;
  origin: string;
  origin_text: string;
  control_twin_ids: string[];
  control_construction: string;
  created_utc: string;
  status: string;
  licence: string;
  shadow?: boolean;
  round_trip_bps?: number;
  zero_cost_diagnostic?: boolean;
  nav: number | null;
  last_mark: string | null;
  n_marks: number;
  since_inception_pct: number | null;
  why_no_nav?: string;
  /** The fleet card's estimability rule, applied to book-minus-twin. */
  vs_twin: FleetLane;
  twins: BookTwin[];
  worst_case: BookWorstCase;
  forecasts: BookForecasts;
  [k: string]: unknown;
}

export interface BooksResponse {
  utc?: string;
  available?: boolean;
  error?: string;
  books?: BookRow[];
  n_books?: number;
  n_twins?: number;
  min_days_for_estimable?: number;
  note?: string;
}

export interface LedgerResponse {
  utc: string;
  available: boolean;
  error?: string;
  path: string | null;
  exists: boolean;
  health?: UnknownPayload;
  calibration_by_model?: UnknownPayload;
  n_open?: number | null;
  graded_last_24h?: number | null;
  graded_note?: string;
  /** Murphy's decomposition (M4). `overall.bins` is the reliability diagram;
   *  `decomposition: "insufficient_n"` means the board draws nothing rather
   *  than drawing a curve through four points. */
  decomposition?: CalibrationReport;
}

export interface CalibrationBin {
  bin_id: number;
  p_lo: number;
  p_hi: number;
  n: number;
  mean_forecast: number;
  mean_outcome: number;
  outcome_se: number;
  overconfidence: number;
}

export interface CalibrationSlice {
  n?: number;
  brier?: number;
  brier_binned?: number;
  binning_residual?: number;
  base_rate?: number;
  climatology_brier?: number;
  beats_climatology?: boolean;
  reliability?: number;
  resolution?: number;
  uncertainty?: number;
  identity_check_abs_error?: number;
  decomposition?: string;
  reason?: string;
  n_bins?: number;
  bins?: CalibrationBin[];
  group_key?: string;
  model?: string;
  note?: string;
}

export interface CalibrationReport {
  as_of?: string;
  available?: boolean;
  error?: string;
  group_by?: string;
  n_resolved?: number;
  min_per_bin?: number;
  min_n_for_decomposition?: number;
  overall?: CalibrationSlice;
  rolling?: CalibrationSlice & { window?: string };
  base_rate_row?: CalibrationSlice & { pit?: boolean; n_no_history?: number };
  persistence?: {
    persistence?: string;
    r?: number;
    n_pairs?: number;
    quarters_scored?: number;
    min_pairs?: number;
    bss_by_quarter?: Record<string, number>;
    reason?: string;
  };
  groups?: Record<string, CalibrationSlice>;
}

export const getUniverse = (opts: {
  offset?: number;
  limit?: number;
  q?: string;
  sort?: string;
  dir?: "asc" | "desc";
} = {}) => {
  const p = new URLSearchParams();
  if (opts.offset) p.set("offset", String(opts.offset));
  if (opts.limit) p.set("limit", String(opts.limit));
  if (opts.q) p.set("q", opts.q);
  if (opts.sort) p.set("sort", opts.sort);
  if (opts.dir) p.set("dir", opts.dir);
  const qs = p.toString();
  return controlFetch<UniverseResponse>(`/universe${qs ? `?${qs}` : ""}`, undefined, 60_000);
};

export const getTree = (root: string) =>
  controlFetch<TreeResponse>(`/tree?root=${encodeURIComponent(root)}`);

export const getFile = (path: string) =>
  controlFetch<FileResponse>(`/file?path=${encodeURIComponent(path)}`, undefined, 30_000);

export const getAppLog = (tail = 200) =>
  controlFetch<AppLogResponse>(`/app-log?tail=${tail}`);

export const getLedger = () => controlFetch<LedgerResponse>("/ledger", undefined, 30_000);

// ------------------------------------------------------------------- morning

export interface MorningStep {
  step: string;
  /** One of ok | nothing_to_do | refused | error | skipped. A refusal names
   *  the missing precondition; "nothing_to_do" is not "ok with zeros". */
  status: string;
  what?: string;
  reason?: string;
  note?: string;
  utc?: string;
  [k: string]: unknown;
}

export interface MorningResponse {
  utc?: string;
  ran?: boolean;
  date?: string;
  run?: number;
  path?: string;
  path_rel?: string;
  dir?: string;
  note?: string;
  elapsed_s?: number;
  network_requested?: boolean;
  declared_steps?: string[];
  steps?: MorningStep[];
  read_me_first?: string;
}

/** The newest morning receipt for a day, or `{ran:false}`. A read. */
export const getMorning = (day?: string) =>
  controlFetch<MorningResponse>(`/morning${day ? `?day=${encodeURIComponent(day)}` : ""}`);

/** Run the morning. Minutes, not seconds: it marks the books and grades. */
export const runMorning = (network = true) =>
  controlFetch<MorningResponse>(
    `/morning?network=${network ? "true" : "false"}`,
    { method: "POST" },
    10 * 60_000,
  );

// ------------------------------------------------- tolerant field readers
// For payloads whose exact keys are not fixed yet. Each returns null when no
// candidate key is present, so the caller renders "—" and never a placeholder.

export function pickString(o: unknown, keys: string[]): string | null {
  if (!o || typeof o !== "object") return null;
  const rec = o as Record<string, unknown>;
  for (const k of keys) {
    const v = rec[k];
    if (typeof v === "string" && v.trim() !== "") return v;
    if (typeof v === "number" && Number.isFinite(v)) return String(v);
  }
  return null;
}

export function pickNumber(o: unknown, keys: string[]): number | null {
  if (!o || typeof o !== "object") return null;
  const rec = o as Record<string, unknown>;
  for (const k of keys) {
    const v = rec[k];
    if (typeof v === "number" && Number.isFinite(v)) return v;
    if (typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v))) {
      return Number(v);
    }
  }
  return null;
}

export function pickBool(o: unknown, keys: string[]): boolean | null {
  if (!o || typeof o !== "object") return null;
  const rec = o as Record<string, unknown>;
  for (const k of keys) {
    if (typeof rec[k] === "boolean") return rec[k] as boolean;
  }
  return null;
}

export function pickObject(
  o: unknown,
  keys: string[],
): Record<string, unknown> | null {
  if (!o || typeof o !== "object") return null;
  const rec = o as Record<string, unknown>;
  for (const k of keys) {
    const v = rec[k];
    if (v && typeof v === "object" && !Array.isArray(v)) {
      return v as Record<string, unknown>;
    }
  }
  return null;
}

export function pickArray(o: unknown, keys: string[]): unknown[] | null {
  if (!o || typeof o !== "object") return null;
  const rec = o as Record<string, unknown>;
  for (const k of keys) {
    if (Array.isArray(rec[k])) return rec[k] as unknown[];
  }
  return null;
}

// ------------------------------------------------------------- N-F coverage

/** One registry source's coverage, as `/api/control/coverage` reports it. */
export interface CoverageSource {
  id: string;
  provider: string;
  region: string;
  language: string;
  tier: string;
  pit_grade: "native_stamp" | "first_seen_only" | "index_state" | string;
  label_source: boolean;
  implemented: boolean;
  rows_total: number;
  rows_today: number;
  trend_7d: number[];
  last_row_utc: string | null;
  last_row_age_hours: number | null;
  last_run_utc: string | null;
  runs: number;
  consecutive_zero_runs: number;
  resolution_rate: number | null;
  status: string;
  flags: string[];
}

export interface CoverageRegion {
  region: string;
  sources: number;
  implemented: number;
  rows_total: number;
  rows_today: number;
  red: string[];
  never_pulled: string[];
  last_row_age_hours: number | null;
}

export interface CoverageResponse {
  utc: string;
  available: boolean;
  error?: string;
  registry?: { version?: string; licence?: string; path?: string };
  corpus_dir?: string;
  corpus_exists?: boolean;
  sources: CoverageSource[];
  regions: CoverageRegion[];
  totals: {
    sources?: number;
    implemented?: number;
    rows_total?: number;
    rows_today?: number;
    red?: string[];
    never_pulled?: string[];
    label_sources?: string[];
    mean_resolution_rate?: number | null;
  };
  asia_first?: {
    regions: string[];
    rows_total: number;
    rows_today: number;
    note: string;
  };
  name_table?: UnknownPayload;
  analyst_snapshots?: {
    dir?: string;
    days?: number;
    series_starts?: string | null;
    latest?: string | null;
    note?: string;
  };
  rules?: UnknownPayload;
}

export const getCoverage = () =>
  controlFetch<CoverageResponse>("/coverage", undefined, 60_000);

// ---------------------------------------------------------- lane A: agency
// `backend/routers/control.py`'s agency block. Four reads and three writes,
// and one rule the types carry: every agency payload has a `limits` sentence
// on it, because the SEC boundary is a property of the payload rather than a
// paragraph somebody remembered to put on one page.

export interface AgencyQuestion {
  qid: string;
  text: string;
  dimension: string;
  scale: string;
  source: string;
}

export interface PersonalityRow {
  personality: string;
  k: number;
  max_single_name: number;
  gross_cap: number;
  stop_loss: number;
  drawdown_budget: number;
  rebalance_frequency: string;
  cash_floor: number;
  extrapolated: boolean;
  sources: Record<string, string>;
  note?: string;
}

export interface QuestionnaireResponse {
  utc?: string;
  version?: string;
  questions?: AgencyQuestion[];
  bands?: Array<{ from: number; to: number; personality: string }>;
  personalities?: Record<string, PersonalityRow>;
  constraint_vocabulary?: { pattern?: string; esg_categories?: string[] };
  convention?: string;
  limits?: string;
}

export interface IntakeResponse {
  utc?: string;
  ips?: UnknownPayload & { ips_hash?: string; personality?: string };
  ips_hash?: string;
  ips_prose_md?: string;
  prose_source?: string;
  prose_rejected?: string | null;
  validated_by?: string;
  numeric_fields?: Record<string, number>;
  personality_numbers?: PersonalityRow;
  echoes?: string[];
  ips_path_rel?: string | UnknownPayload;
  limits?: string;
}

export interface PlainWords {
  number: string;
  sentence: string;
  receipt_path: string;
  missing_fields?: string[];
  source?: string;
  draft_rejected?: string;
}

export interface AgencyOptionRow {
  personality: string;
  is_declared_choice: boolean;
  contract_hash: string;
  strategy_id?: string;
  title?: string;
  signal?: string;
  k?: number;
  max_single_name?: number;
  gross_cap?: number;
  stop_loss?: number;
  drawdown_budget?: number;
  cash_floor_pct?: number;
  notional_usd?: number;
  cadence?: string;
  hold_rule?: string;
  extrapolated_tier?: boolean;
  worst_case?: {
    worst_case_usd?: number | null;
    worst_case_pct_of_equity?: number | null;
    gross_over_equity?: number;
    verdict?: string;
    equity_basis?: string;
  };
  expected_drawdown?: {
    verdict?: string;
    why?: string;
    worst_twin_drawdown?: number;
    drawdown_budget?: number | null;
    n_twin_marks?: number;
  };
  twins?: Array<{ book_id: string; kind?: string | null; construction?: string }>;
  plain_words?: PlainWords[];
  cost_curve?: string;
  round_trip_bps?: number;
  [k: string]: unknown;
}

export interface ProposeResponse {
  utc?: string;
  ips_hash?: string;
  ips_id?: string;
  declared_personality?: string;
  capital_usd?: number;
  cash_floor_pct?: number;
  n_options?: number;
  options?: AgencyOptionRow[];
  how_to_hold?: string;
  the_choice_is_graded?: string;
  limits?: string;
}

export interface HoldResponse {
  utc?: string;
  held_utc?: string;
  ips_hash?: string;
  chosen_book_id?: string;
  chosen_contract_hash?: string;
  sentence?: string;
  books?: Array<{ role: string; book: UnknownPayload; twins: UnknownPayload[] }>;
  note?: string;
  limits?: string;
}

export interface ReviewCall {
  book_id?: string;
  ticker: string;
  decision: string;
  probability: number;
  prediction_id: string;
  row_hash: string;
}

export interface AgencyReviewResponse {
  utc?: string;
  ran?: boolean;
  date?: string;
  status?: string;
  reason?: string;
  n_books?: number;
  n_calls?: number;
  n_refused?: number;
  calls?: ReviewCall[];
  refused?: Array<{ book_id?: string; ticker?: string; reason?: string }>;
  protect_first?: UnknownPayload;
  vocabulary?: string[];
  receipt_rel?: string | null;
  note?: string;
  limits?: string;
}

export interface ProtectFirstResponse {
  utc?: string;
  n_flips?: number;
  n_open?: number;
  flips?: UnknownPayload[];
  ledger_rel?: string;
  reading?: string;
  limits?: string;
}

// ---------------------------------------------------------------- the reader
// `backend/services/reader_control.py` via `/api/control/reader*` (CH-22b).
// The one switch for the web reader; it replaces AegisReaderControl.exe.

export interface ReaderStamp {
  utc: string | null;
  age_s: number | null;
  freshness: "FRESH" | "STALE" | "FUTURE" | "UNDATEABLE" | "MISSING";
}

export interface ReaderMarker {
  name: string;
  present: boolean;
  owner: "absent" | "this_app" | "retired_controller" | "supervisor_repair" | "other";
  content: string | null;
  written_utc: string | null;
}

export interface ReaderStatus {
  utc: string;
  desired: "ON" | "OFF";
  actual: string;
  actual_words: string;
  what_will_happen: string;
  stop_marker: ReaderMarker;
  pool_stop_marker: ReaderMarker;
  supervisor: {
    readable: boolean;
    why?: string | null;
    state?: string | null;
    stamp?: ReaderStamp;
    freshness: string;
    pages_ok_10m?: number | null;
    pages_ok_60m?: number | null;
    classes_60m_by_host?: Record<string, Record<string, number>>;
    current_hosts?: string[];
    next_action?: string | null;
    last_error?: string | null;
    restarts?: number | null;
    free_ram_gb?: number | null;
    mode?: string | null;
    pool_pid_as_reported?: number | null;
  };
  supervisor_log: {
    readable: boolean;
    supervisor_pid_as_logged?: number | null;
    started?: ReaderStamp;
    until?: string | null;
    ended?: ReaderStamp;
    ended_why?: string | null;
  };
  pool: {
    status: { readable: boolean; stamp?: ReaderStamp; freshness: string;
              pid_as_reported?: number | null; state?: string | null };
    startup: { readable: boolean; stamp?: ReaderStamp; freshness: string;
               pid_as_reported?: number | null; state?: string | null; phase?: string | null };
  };
  pages: {
    readable: boolean;
    last_ok: ReaderStamp;
    ok_10m?: number;
    ok_60m?: number;
    ok_60m_by_host?: Record<string, number>;
    invalid_rows?: number;
  };
  disk: { free_gb: number | null; floor_gb: number | null; below_floor: boolean | null };
  gateway: { host?: string; port?: number; answers: boolean | null };
  chrome: { host?: string; port?: number; answers: boolean | null };
  handoff_present: boolean;
  iif_quiet_now: boolean | null;
  retired_controller: { actual_state: string | null; last_error: string | null } | null;
  fresh_limit_s: number;
}

export interface ReaderOnResponse {
  ok: boolean;
  action: string;
  detail: string;
  decision: Record<string, unknown>;
  status: ReaderStatus | null;
}

export interface ReaderOffResponse {
  ok: boolean;
  result: "STOP_REQUESTED" | "STOPPED" | "HELD_BY_OTHER" | "CANNOT_DETERMINE";
  wrote_marker?: boolean;
  detail: string;
  status?: ReaderStatus;
}

export const getReader = () => controlFetch<ReaderStatus>("/reader");
/** The process scan inside `ensure_reader` can take up to a minute. */
export const readerOn = () => post<ReaderOnResponse>("/reader/on", undefined, 120_000);
export const readerOff = () => post<ReaderOffResponse>("/reader/off", undefined, 30_000);

export const getQuestionnaire = () =>
  controlFetch<QuestionnaireResponse>("/agency/questionnaire");
export const getAgencyReview = (day?: string) =>
  controlFetch<AgencyReviewResponse>(
    `/agency/review${day ? `?day=${encodeURIComponent(day)}` : ""}`,
  );
export const getProtectFirst = () =>
  controlFetch<ProtectFirstResponse>("/agency/protect-first");

export interface IntakeBody {
  capital: number;
  horizon_months: number;
  personality: string | null;
  constraints: string[];
  liquidity_need: number;
  answers: number[];
  draft?: boolean;
}

/** A1. Gated: it may ask the local model for the prose. Writes no book. */
export const agencyIntake = (body: IntakeBody) =>
  post<IntakeResponse>("/agency/intake", body, 180_000);

/** A2. Writes nothing — the books exist only once a human holds one. */
export const agencyPropose = (ipsHash: string) =>
  post<ProposeResponse>("/agency/propose", { ips_hash: ipsHash }, 120_000);

/**
 * A2. The ONLY call that mints `origin="human_text"`.
 *
 * The sentence is not optional and the client does not invent one: it is what
 * makes the book the person's, and the backend refuses a short one rather
 * than accepting a blank reason.
 */
export const agencyHold = (
  ipsHash: string,
  chosenContractHash: string,
  sentence: string,
) =>
  post<HoldResponse>(
    "/agency/hold",
    { ips_hash: ipsHash, chosen_contract_hash: chosenContractHash, sentence },
    120_000,
  );

// ---------------------------------------------------------------- ticker hub (CH-22)
// Mirrors `backend/routers/ticker_hub.py` / `backend/services/ticker_hub.py`. Local
// only: both routes answer 403 unless the desktop shell set AEGIS_CONTROL_ENABLED=1,
// so on the public site the callers render nothing.

export interface HubTag {
  t: string;
  /** source_field | sec_cik | reader_lane | reader_search | digest_typed | text_token | name_match */
  m: string;
  rule: string | null;
  where: string | null;
}

export interface HubNewsRow {
  id: string;
  source: string;
  publisher: string | null;
  kind: string | null;
  first_seen_utc: string | null;
  published_utc: string | null;
  title: string | null;
  url: string | null;
  feeds: string[] | null;
  regions: string[] | null;
  tags: HubTag[];
  event: { event_type: string | null; topic: string | null; sentiment: number | null; model: string | null } | null;
  tagged_by?: string[];
}

export interface HubForecast {
  id: string | null;
  made_at: string | null;
  specialist: string | null;
  observable: string | null;
  probability: number | null;
  threshold: number | null;
  benchmark: string | null;
  horizon_days: number | null;
  resolves_after: string | null;
  resolved_at: string | null;
  outcome: number | null;
  brier: number | null;
  realised_return: number | null;
  void_reason: string | null;
  model: string | null;
  thesis: string | null;
}

export interface HubCoverage {
  status: "OK" | "STALE" | "NO_INDEX";
  index_built_utc: string | null;
  index_age_s: number | null;
  stale_after_s: number;
  detail: string | null;
  rows_in_index?: number | null;
  untagged_share_last_build?: number | null;
  newest_per_source?: Record<string, string>;
}

export interface TickerHubResponse {
  schema: string;
  ticker: string;
  siblings: string[];
  days: number;
  now_utc: string;
  identity: { name: string | null; sector: string | null; gics_sector: string | null } | null;
  news: HubNewsRow[];
  forecasts: {
    status: string;
    open: HubForecast[];
    resolved: HubForecast[];
    void: HubForecast[];
    counts: {
      open: number;
      resolved: number;
      void: number;
      resolved_outcome_1?: number;
      resolved_outcome_0?: number;
      mean_brier?: number | null;
      n_brier?: number;
    };
  };
  calendar: {
    status: string;
    label?: string | null;
    last_reported?: string | null;
    error?: string;
    rows: {
      date: string | null;
      kind: string | null;
      label: string | null;
      confirmation: string | null;
      timing: string | null;
      days_away: number | null;
      sessions_away: number | null;
      source: string | null;
    }[];
  };
  events: {
    event_id: string;
    primary_ticker: string;
    role: string;
    link: string;
    link_quality: string;
    first_seen_utc: string;
    importance_at: number | null;
    n_publishers: number | null;
    n_evidence: number | null;
    title: string | null;
  }[];
  related: {
    ticker: string;
    name: string | null;
    link: string;
    weight: number | null;
    n: number | null;
    sign: number | null;
    source: string;
    graph_build_id: string | null;
  }[];
  coverage: HubCoverage & {
    n_rows: number;
    n_returned: number;
    truncated: boolean;
    sources: Record<string, number>;
    tagged_by: Record<string, number>;
    newest_utc: string | null;
  };
}

export interface NewsFeedFacet {
  key: string;
  n: number;
  name?: string | null;
}

export interface NewsFeedResponse {
  schema: string;
  now_utc: string;
  days: number;
  filters: { ticker: string | null; sector: string | null; source: string | null };
  rows: HubNewsRow[];
  n_rows: number;
  n_returned: number;
  truncated: boolean;
  facets: { ticker: NewsFeedFacet[]; sector: NewsFeedFacet[]; source: NewsFeedFacet[] };
  sectors: string[];
  coverage: HubCoverage;
}

export const getTickerHub = (symbol: string, days = 30) =>
  controlFetch<TickerHubResponse>(
    `/ticker/${encodeURIComponent(symbol)}/hub?days=${days}`,
  );

export const getNewsFeed = (q: {
  ticker?: string;
  sector?: string;
  source?: string;
  days?: number;
  limit?: number;
}) => {
  const p = new URLSearchParams();
  if (q.ticker) p.set("ticker", q.ticker);
  if (q.sector) p.set("sector", q.sector);
  if (q.source) p.set("source", q.source);
  p.set("days", String(q.days ?? 30));
  p.set("limit", String(q.limit ?? 200));
  return controlFetch<NewsFeedResponse>(`/news/feed?${p.toString()}`);
};

/** True when the ticker-hub routes are simply not available here (public site,
 *  backend down, older backend) -- the caller then renders nothing at all. */
export function hubUnavailable(e: unknown): boolean {
  return isForbidden(e) || isUnreachable(e) || (isNotBuilt(e) && !String((e as ControlError).detail).includes("not in the universe"));
}

// ---------------------------------------------------------------- owner inbox
// CH-22 (2026-11-14): `backend/routers/owner_inbox.py`. A note is one
// append-only row the NEXT Claude session reads at its start
// (`python -m scripts.owner_inbox list --unread`). It is not a chat: nothing is
// sent anywhere and no model answers it.

/**
 * Whether this build talks to the local control plane at all. The packaged
 * desktop app is the only build that does (`AEGIS_DESKTOP_BUILD=1` ->
 * `NEXT_PUBLIC_AEGIS_DESKTOP_BUILD=1`, the same flag `lib/api.ts` uses for its
 * same-origin base). On the public website it is false at COMPILE time, so the
 * "This PC" links and the note box are not in the page at all.
 */
export const CONTROL_PLANE_BUILD = process.env.NEXT_PUBLIC_AEGIS_DESKTOP_BUILD === "1";

export interface OwnerNote {
  kind: "note";
  id: string;
  utc: string;
  text: string;
  page: string | null;
  status: "unread" | "read";
  status_utc?: string | null;
}

export interface OwnerNoteSaved {
  saved: boolean;
  path: string;
  note: OwnerNote;
}

export interface OwnerNotesResponse {
  path: string;
  exists: boolean;
  n_notes: number;
  n_unread: number;
  unreadable_lines: number;
  notes: OwnerNote[];
}

/** Gated (403 unless the desktop shell enabled the control plane). 422 = empty or too long. */
export const postOwnerNote = (text: string, page?: string | null) =>
  post<OwnerNoteSaved>("/owner-note", { text, page: page ?? null });

/** Newest first. Gated like the write: the owner's notes are never public. */
export const getOwnerNotes = (limit = 5) =>
  controlFetch<OwnerNotesResponse>(`/owner-notes?limit=${limit}`);
