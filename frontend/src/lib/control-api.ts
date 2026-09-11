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

const DESKTOP_BUILD = process.env.NEXT_PUBLIC_AEGIS_DESKTOP_BUILD === "1";

/** Same origin inside the packaged app; the dev backend otherwise. */
export const CONTROL_BASE = DESKTOP_BUILD
  ? ""
  : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
/** Not in the router yet either; the Fleet page renders "not available" on 404. */
export const getFleet = () => controlFetch<FleetResponse>("/fleet");

// ---------------------------------------------------------------- writes

export const runJob = (job: string, hours?: number) =>
  post<StartedRun>(
    `/run/${encodeURIComponent(job)}${hours != null ? `?hours=${hours}` : ""}`,
  );
export const runNight = (hours: number) => post<StartedRun>(`/night?hours=${hours}`);
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
