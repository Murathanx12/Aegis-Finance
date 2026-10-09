# OpenClaw and local Qwen runtime check — 2026-10-08

This is a local operational check, not a strategy or model quality result. No
secrets, private browser tabs, or account pages were inspected.

## What is wired

- Aegis calls OpenClaw in two ways. `openclaw_client.agent()` selects an explicit
  model for an LLM turn and writes a telemetry row; existing callers select
  DeepSeek. `openclaw_client.browser()` uses deterministic verbs and no model.
- The configured `aegis-local` provider points to the loopback OpenAI-compatible
  endpoint on port 8080 and names `Qwen2.5-7B-Instruct-Q4_K_M`. It is available
  for an explicit model choice, not selected as the default for `main`.
- Global and `main` tool profiles are `minimal`; `main` denies `browser`.
  `aegis-browser` has `minimal + browser` solely for the guarded HTTP transport.
  The offline 24-hour scope audit returned `OK`, 0 config problems, 0 model tool
  calls, 0 violations, and 0 transcript errors. Zero calls does not prove a
  working live agent.
- `backend/services/browser_policy.py` limits the research browser to reads;
  payments, messages, social actions and account controls are refused.
  `scripts/openclaw_login.py` has Google and Reddit credential-fill steps, but
  `fill` is absent from the current operator verb set, and the Google host is
  outside the research allowlist. This legacy command is therefore not a
  working login path. The separate sign-up design dated 2026-09-29 is unbuilt.

## Local observations and one repair attempt

At 16:44 Singapore time, gateway port 18789 and Qwen port 8080 were closed.
The dedicated MuratClaw Chrome CDP port 18802 was open and its read-only version
endpoint answered Chrome 155 / CDP 1.3. Another CDP port was open but was not
used because its browser ownership was not established. The local Qwen binary
and exact 7B GGUF named above are present, with no model server listening. The
model operator hold was absent. Free physical RAM was 3.96 GiB, and the IIF-1
night launcher and reader supervisor were present. No service was started in
the 16:45–17:05 protected window.

At 20:56, RAM was 5.10 GiB, the model hold was still absent, and both gateway
and dedicated CDP ports were down. One call to the existing
`gateway_repair.repair("GATEWAY_DOWN")` launched the dedicated Chrome and called
the scheduled gateway start. It waited its full configured port budget, then
returned unhealthy with `gateway did not bind its port within the wait; not
restarting a gateway that may still be starting`. The dedicated CDP port was
then up; gateway port 18789 remained closed. `openclaw gateway status` reported
the Scheduled Task as running, but its connectivity probe failed with
`ECONNREFUSED`. Windows Task Scheduler gave `OpenClaw Gateway` state Running
and result `267009` (`0x41301`, task still running); its VBS and CMD wrapper
processes existed, but no Node gateway child or port listener did. The last-run
PID shown by OpenClaw was absent. This stale wrapper appears to prevent
`gateway start` from launching a fresh child; that is an inference from the
process tree and failed start, not a verified root cause. Eight dedicated Chrome
child processes were present. Free RAM after the attempt was 3.95 GiB. The
gateway cannot presently serve a guarded `browser("status")` call. No model
request was made, no paid fallback was used, and there was no second gateway
start or restart. The local Qwen server remained down. The task owner redirected
work to a separate hook failure, so runtime/model testing stopped here.

## Safe proof and operating path

1. Diagnose why the scheduled gateway task exits without binding its port;
   inspect its exit result and sanitized gateway log. Avoid a repeated start
   while that state is unresolved. The existing owner is `gateway_repair` via
   `scripts.night_reader_supervisor --repair-once`; it respects the gateway RAM
   floor and avoids a second gateway tree. Do not restart a gateway that is
   still coming up.
2. After a healthy gateway, call `openclaw_client.browser("status",
   profile_name="muratclaw")` and record only return code and running state.
   No tab listing, navigation or account interaction is needed for this proof.
3. For a local model smoke, check sufficient available RAM and no operator
   hold, then use `llama_server.ensure()` and wait for `/health` ready. Submit
   one synthetic, nonsecret extraction using the explicit `aegis-local` model.
   Record the served model and latency, release the test session, and let the
   owned idle reaper stop the server. Never fall back to a paid model.

Keep browser writes in a separately scoped deterministic workflow for named,
authorized account tasks. Do not widen the research reader or grant browser,
shell, or file tools to the OpenClaw LLM agent.

Sources: `backend/services/openclaw_client.py`, `openclaw_http.py`,
`openclaw_tool_scope.py`, `browser_policy.py`, `gateway_repair.py`,
`llama_server.py`; `scripts/openclaw_login.py`,
`docs/research_notes/2026-09-29/openclaw_tool_scope_2026-09-29.md`, and
`browser_signin_signup_design_2026-09-29.md`.
