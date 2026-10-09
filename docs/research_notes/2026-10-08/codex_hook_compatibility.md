# Codex SessionStart hook compatibility — 2026-10-08

The existing `scripts/session_state.py` emits a bare JSON state object for Claude Code. Codex expects SessionStart context as plain text or `hookSpecificOutput` with `hookEventName: SessionStart` and string `additionalContext` ([Codex hooks documentation](https://learn.chatgpt.com/docs/hooks)). A bare state object has no recognized context field.

`.codex/hooks/session_start.py` now imports the unchanged `build_state()` from the repository path and wraps its result as Codex `additionalContext`. Import or probe failure becomes explicit `Aegis session state unavailable: <type>: <reason>` context. `.codex/hooks.json` points only the Codex hook at this adapter. Its 105-second outer timeout exceeds the state builder's bounded sequential probes: four Git calls at up to 15 seconds each, one health call at 15 seconds, and two calls at 6 seconds each (87 seconds total, before local work and overhead).

Independent review caught the relative registered command and the shared builder's mtime-based document pointers. The Codex registration now resolves its script from `git rev-parse --show-toplevel`; its context points at `docs/INDEX.md` rather than presenting checkout-time ordering as freshness. The original shared builder is unchanged.

Verification after those fixes: `.venv\Scripts\python.exe -m pytest backend/tests/test_codex_session_hook.py -q` passed **5 tests**. The added regression executes the registered command from a nested folder in a temporary Git repo whose path contains spaces, with an offline state stub.

## Remaining exit-code-1 errors, reproduced and resolved in Codex config

The imported security-guidance plugin was disabled and native Codex Security 0.1.32 installed. A subsequent owner report of exit code 1 led to deterministic reproduction of two other imported hooks under the installed PowerShell:

- Vercel's `node "${CLAUDE_PLUGIN_ROOT}/hooks/session-start-seen-skills.mjs"` exits 1: the Bash-style variable is empty in PowerShell, so Node looks for `C:\hooks\session-start-seen-skills.mjs`.
- The explanatory-style hook exits 1 because bare `bash` resolves to the Windows WSL shim, whose `/bin/bash` cannot start in that environment.

Only Codex hook state was changed: the 12 security-guidance handlers are explicitly disabled as well as their plugin; the 5 Vercel and 1 explanatory-style handlers are disabled individually. Their plugin skills remain available. Aegis SessionStart remains enabled/trusted. All original Claude files and marketplace source files remain intact. Backups are under `~/.codex/`.

Final fresh-process `hooks/list`: **0 errors, 0 warnings, 1 enabled/trusted project SessionStart, 6 loaded-but-disabled imported handlers, 0 security-guidance handlers loaded**. The actual registered Aegis command was executed through PowerShell from `backend/`: **exit 0, 5.94 seconds, valid SessionStart context, no stderr, local and production state OK**. No active security-hook reviewer processes were found. The check used no model turn or security scan; the preserved hook itself performs only read-only state probes.

A new `thread/start` RPC succeeded but emitted no hook events until a turn, so that call is not claimed as proof of model-context delivery. Starting a paid model turn solely to repeat this check was deliberately avoided. An already-open client can retain an old handler snapshot until a new chat or restart.
