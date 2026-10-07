# Q18: the build environment was lying about `NEXT_PUBLIC_API_URL` — fixed 2026-10-07

## The finding

Live site, 2026-10-07 16:43 HKT, deploy of main `92f147f6`. The browser
console on every page printed:

```
[aegis] NEXT_PUBLIC_API_URL is not an absolute http(s) URL (got 11 chars
starting "["); using https://aegis-finance-production.up.railway.app.
Fix the build environment.
```

`vercel env ls` showed the Project variable `NEXT_PUBLIC_API_URL` set
(Production, Encrypted) to the real Railway URL — the orchestrator had
replaced it on 2026-10-06. The build still inlined the 11-character string
`[SENSITIVE]`. The site worked at all only because of
`frontend/src/lib/api.ts`'s `resolveApiBase` (C4, 2026-10-06), which refuses
a non-absolute value and falls back to the hardcoded `PUBLIC_API_FALLBACK`.

## The cause

Vercel's CLI **redacts** a Project environment variable marked "Sensitive"
the moment you read it back through the CLI: `vercel env pull` and
`vercel pull` both write the literal 11-character placeholder string
`"[SENSITIVE]"` into the pulled `.env.production.local` file instead of the
real value — a deliberate anti-leak feature of the CLI, not a bug in it. A
`vercel env pull` run on the local dev machine reproduced this exactly:
`NEXT_PUBLIC_API_URL="[SENSITIVE]"` on disk.

The deploy workflow (`.github/workflows/deploy-frontend-vercel.yml`) runs
`vercel pull --environment=production` and then `vercel build --prod`.
`vercel build` reads whatever `vercel pull` wrote to
`.vercel/.env.production.local` and exposes it to the framework build as an
environment variable. Next.js inlines every `NEXT_PUBLIC_*` variable into the
client bundle at build time (webpack `DefinePlugin`-style substitution), so
the literal string `[SENSITIVE]` — not the real URL — was compiled into every
page's JavaScript. Nothing failed at build time: `[SENSITIVE]` is a
syntactically valid string, so there was no type error, no bundler error, no
CI red. It only surfaced as a runtime console warning because C4's `api.ts`
guard (added the day before, for an unrelated earlier instance of the exact
same placeholder) happened to validate the value and print a loud message
when it was wrong.

The chain, end to end:
1. Someone marks the Vercel Project variable "Sensitive" (or it was already
   marked that way) — a reasonable thing to do for an API key, wrong for a
   public URL.
2. `vercel pull` / `vercel env pull` cannot read a Sensitive variable's value
   back through the CLI at all, by design, and substitutes `[SENSITIVE]`.
3. `vercel build` consumes that pulled file and exposes `[SENSITIVE]` as
   `process.env.NEXT_PUBLIC_API_URL`.
4. Next.js inlines it into the browser bundle, unconditionally, at build
   time — there is no runtime indirection to intercept.
5. The only thing between that and a totally broken site was the `api.ts`
   fallback, which is a mercy, not a fix: every request for 6+ weeks (per the
   2026-10-06 note that found this the first time) ran against the fallback
   host rather than whatever the operator intended when setting the variable.

## The fix (this commit)

1. **`.github/workflows/deploy-frontend-vercel.yml`** — the Build step now
   sets `NEXT_PUBLIC_API_URL: https://aegis-finance-production.up.railway.app`
   explicitly in its own `env:` block, with a comment explaining it is a
   PUBLIC URL (not a secret) and why it must be set this way: a variable
   already present in the process environment when the build command runs is
   never overwritten by Next's own `.env` loading, so this wins over whatever
   `vercel pull` wrote to `.vercel/.env.production.local`, regardless of how
   the Project variable is marked in the Vercel dashboard. `vercel pull`
   stays for every other variable (API keys, org/project IDs) — this is the
   one value pinned in the workflow because it is public and because getting
   it wrong breaks the whole site silently.
2. **A post-build guard**, in two places sharing one implementation:
   - `scripts/frontend_check.py`: `guard_bundle_for_redacted_api_url(dir)`
     greps every emitted `.js` chunk under `dir` for the literal
     `[SENSITIVE]` and for the Railway host string
     `aegis-finance-production.up.railway.app`. It is exposed on the CLI as
     `python -m scripts.frontend_check --guard-api-url-dir DIR`, which runs
     only the guard (no build) and exits 1 if the placeholder is found or the
     host string is absent, 0 otherwise, `CANNOT DETERMINE` (exit 0, no
     verdict) if the directory doesn't exist or holds no `.js` files.
   - The workflow adds a step, **Guard built bundle against the Vercel CLI's
     redaction placeholder**, between Build and Deploy, calling
     `python3 -m scripts.frontend_check --guard-api-url-dir
     frontend/.vercel/output/static` (the directory `vercel build` writes).
     A red guard fails the job before `vercel deploy --prebuilt` ever runs,
     so a regression never reaches production.
   - Deterministic tests in `backend/tests/test_frontend_check_api_url.py`
     exercise the guard against fixture directories only (one chunk carrying
     the placeholder, one clean, one carrying the real host, one with
     neither) — no real `next build` or `vercel build` runs in the suite.
     Three further tests pin that `PUBLIC_API_FALLBACK` in
     `frontend/src/lib/api.ts`, the workflow's `NEXT_PUBLIC_API_URL:` line,
     and the guard's own `EXPECTED_API_URL` constant all name the same host,
     so the three cannot drift apart silently the way the Vercel dashboard
     variable and the code's fallback already had.

## What this does NOT fix, and the owner-facing instruction

The workflow's explicit env var wins regardless of how the Vercel dashboard
variable is configured, so the site is safe either way. But the dashboard
variable itself is still wrong-shaped for what it holds:

- **Un-mark `NEXT_PUBLIC_API_URL` as "Sensitive" in the Vercel dashboard**
  (Project → Settings → Environment Variables), or delete it outright. It is
  a public URL — the same one in README.md, in the client bundle for anyone
  to read with devtools, and now in this workflow file in plain text. Marking
  it Sensitive buys no confidentiality (it ships to every browser) and costs
  the ability to `vercel env ls`/`pull` it for debugging, which is exactly
  what hid this problem the first time.
- If it is left Sensitive, nothing breaks — the workflow's own `env:` value
  overrides it — but any future automation or developer that re-introduces a
  flow where `vercel build` runs *without* this workflow's explicit env
  var (e.g. a manual `vercel build` on a laptop after a bare `vercel pull`)
  will reproduce the original bug outside CI, where the guard does not run.

## How to verify after the next deploy

1. Open the live site in a browser with devtools open and check the console
   on first load of any page: there must be **no** `[aegis] NEXT_PUBLIC_API_URL
   is not an absolute http(s) URL` line. Its absence is the proof; its
   presence means the build still inlined something other than the real URL.
2. Pull one built JS chunk from the deployed site and grep it:
   ```bash
   curl -s https://aegis-finance-six.vercel.app/ | grep -o '/_next/static/chunks/[A-Za-z0-9._-]*\.js' | head -1
   # then, for that path:
   curl -s https://aegis-finance-six.vercel.app/_next/static/chunks/<name>.js \
     | grep -c 'aegis-finance-production.up.railway.app'
   # expect a nonzero count; and:
   curl -s https://aegis-finance-six.vercel.app/_next/static/chunks/<name>.js \
     | grep -c '\[SENSITIVE\]'
   # expect 0
   ```
3. Confirm the Actions run for the deploy shows the new "Guard built bundle
   against the Vercel CLI's redaction placeholder" step as green, between
   Build and "Deploy to production", in the run's log.

## Files changed

- `.github/workflows/deploy-frontend-vercel.yml` — explicit `NEXT_PUBLIC_API_URL`
  in the Build step's `env:`; new guard step before Deploy.
- `scripts/frontend_check.py` — `API_URL_REDACTION_PLACEHOLDER`,
  `EXPECTED_API_URL`/`EXPECTED_API_HOST`, `guard_bundle_for_redacted_api_url()`,
  and a `--guard-api-url-dir DIR` CLI mode.
- `backend/tests/test_frontend_check_api_url.py` — new, 13 deterministic tests
  (fixture-only; no real build).
