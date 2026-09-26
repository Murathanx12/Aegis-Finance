# OpenClaw localService for the on-box model — 2026-09-26 (chunk G)

## What was changed, exactly

**File:** `C:\Users\mrthn\.openclaw\openclaw.json`
(backup taken first: `openclaw.json.bak_localservice_2026-09-26`).

**Key added:** `models.providers.aegis-local` — nothing else. A before/after
comparison of every top-level key showed only `models` is new; `agents`,
`auth` (the `deepseek:manual` profile), `gateway`, `browser`, `channels` and
`plugins` are byte-identical. **No agent's default model was changed**:
OpenClaw agents still answer with DeepSeek unless a turn selects
`aegis-local/<model>` explicitly.

Applied with the CLI, not by hand, so the gateway's own schema checked it:

```
openclaw config set models.providers.aegis-local "<json>" --strict-json --dry-run
  -> Dry run successful: 1 update(s) validated against ~\.openclaw\openclaw.json.
openclaw config set models.providers.aegis-local "<json>" --strict-json
  -> Updated models.providers.aegis-local. Change will apply without restarting the gateway.
openclaw config validate --json
  -> {"valid":true,"path":"C:\\Users\\mrthn\\.openclaw\\openclaw.json","warnings":[]}
```

The shape is OpenClaw 2026.9.5's documented `localService`
(`node_modules/openclaw/docs/gateway/local-model-services.md`):

| key | value | why |
|---|---|---|
| `baseUrl` | `http://127.0.0.1:8080/v1` | the port `llama_server.py` uses, so the two share ONE server |
| `api` | `openai-completions` | llama-server's OpenAI-compatible route |
| `apiKey` | `aegis-local` | a placeholder; llama-server has no auth and binds loopback |
| `localService.command` | `C:\Users\mrthn\llama\bin\llama-server.exe` | absolute, as required (no PATH lookup) |
| `localService.args` | the same argv `llama_server.start()` builds (`-m`, host, port, `-ngl`, `-c`, `--no-webui`, batch 512 / ubatch 128) | one server shape whichever side starts it; the conservative TDR batch sizes carry over |
| `localService.healthUrl` | `http://127.0.0.1:8080/health` | `/health` is 200 only once weights are resident (measured 2026-09-10); `/v1/models` answers earlier |
| `localService.readyTimeoutMs` | `240000` | = `MODEL_ROUTING_ENSURE_WAIT_S` |
| `localService.idleStopMs` | `900000` | = `MODEL_ROUTING_IDLE_SHUTDOWN_S` (900 s) |

## How the two starters coexist

Both sides follow the same rule: **reuse a healthy server, never adopt it.**

* OpenClaw: "If another … process already has a healthy server at the same
  `healthUrl`, this process reuses it without adopting it (each process only
  manages the child it personally started)." (its docs, quoted)
* Aegis: `llama_server.ensure(reason)` reuses anything listening; a server it
  did not start is `foreign` and is never stopped by the idle watchdog.

So whichever starts first owns the stop, and each stops only its own child
after 15 idle minutes.

## What /research does

`/research <ticker>` = the thesis-card quest (`thesis_card.quest_prompt`)
through `openclaw_client.agent` (DeepSeek does the browsing, as before), then
`thesis_card.synthesize` with the LOCAL model as the synthesiser via
`llm_analyzer.call_named("local", …)` → `llama_server.ensure("telegram:/research")`.

## Not verified

* No OpenClaw turn has yet selected `aegis-local/Qwen2.5-7B-Instruct-Q4_K_M`,
  so OpenClaw's own spawn → ready → idle-stop of this entry is **configured and
  schema-valid, not exercised**. A real exercise starts a multi-GB model and was
  out of scope on a ~5 GB-free machine.
* The argv mirrors `llama_server.py`'s env-resolved values at the time of
  writing (the 7B model). If `AEGIS_LLAMA_MODEL` is pointed at the 30B-A3B, this
  entry must be re-generated (it also needs `--n-cpu-moe`).

## Undo

`openclaw config unset models.providers.aegis-local`, or restore
`openclaw.json.bak_localservice_2026-09-26`.
