# Sign-in / free sign-up for the browser agent: a design for the owner's decision (2026-09-29)

**Status: NOT BUILT. Nothing in this note runs.** The owner's standing permission (2026-09-28): the
browser agent "can sign in or sign up anything using muratclaw mail as long as its free". The task
type was specified in `docs/research_notes/2026-09-28/lane_o_build_2026-09-28.md` §10C and never
built. This note says what building it would take, so the owner can say yes, no, or "only for X".

## RESULTS SCOREBOARD

| line | value |
|---|---|
| RESULT IMPROVEMENT (money) | **NONE**. A design only |
| Code changed | none |
| What the owner decides | (1) build it or not; (2) the first three sites, by name; (3) whether a human clicks the final "Create account" button (recommended) |

## 1. Why the reader cannot do it today, on purpose

Every rule that keeps the reader read-only refuses a sign-up by name:

- `type`, `fill` and `evaluate` are not in the operator verb allowlist (`openclaw_client.OPERATOR_VERBS`), so
  the client refuses them on the dedicated profile by name;
- a click must land on a LINK the snapshot carried, and `web_reader.DENY_LINK_TEXT` refuses
  "sign in / sign up / register / account / subscribe / trial";
- the host allowlist (`config.OPENCLAW_BROWSER_HOSTS`) does not contain `accounts.google.com` or
  any sign-up host;
- `NEVER_HOSTS` (mail, brokerage, Railway, messaging) stays refused whatever a task says.

A sign-up task therefore cannot be a flag on the reader. It has to be a separate task type with its
own, narrower door, so that loosening it never loosens the reader.

## 2. What it would need (the smallest safe version)

1. **A task record written before the first action** (`backend/data/optimus/browser_tasks/<id>.json`):
   site, purpose (which data it unlocks, which lane uses it), the account (the MuratClaw Google
   account only, never the owner's own), the exact fields to be filled (name, email; nothing else),
   the price the site states for the plan being chosen (must read `0` / "free"), and the owner's
   standing permission quoted with its date.
2. **Hosts for this task only**: the target site's sign-up host + `accounts.google.com`
   (for "Sign in with Google"). They are added to a per-task allowlist that dies with the task; they
   are never appended to `OPENCLAW_BROWSER_HOSTS`.
3. **Actions**: click only elements whose visible text matches a fixed allowlist ("Sign up",
   "Sign in", "Sign in with Google", "Continue with Google", "Continue as ...", "Create free account",
   "Register", "Next", "Continue"); type only into fields whose accessible label is on a field
   allowlist (name, email, username). One task = at most ~20 actions; then stop.
4. **A screenshot before every submit**, stored with the task record, and one after.
5. **No password is ever typed by the agent.** Google sign-in on the MuratClaw account is a session
   the owner established by hand; if Google asks for the password, the task stops (see §3).
6. **Refusals by name, pinned by offline tests, before any live use** (the same shape as
   `browser_policy`'s tests): each guard in §3 has a test that feeds a snapshot containing the
   trigger and asserts `STOP_ASK_OWNER`.
7. **One live dry run, attended**: the owner watches the first sign-up end to end.

## 3. The guard list (every item = STOP and ask the owner, never "work around")

| trigger (seen on the page, snapshot text or field label) | action |
|---|---|
| any price other than 0 / "free" for the chosen plan; "free trial" that asks for a card; "billing", "payment method", "card number", "CVC", "expiry", "IBAN", "PayPal", "Apple Pay", "Google Pay" | STOP. **No payment field is ever focused, typed into, or clicked** |
| host is a brokerage, bank, payment, crypto exchange, mail or messaging host (`NEVER_HOSTS`, `openclaw_client.check_url` substring list, `browser_policy.MESSAGE_HOSTS`) | REFUSE before navigating |
| a CAPTCHA / "verify you are human" / hCaptcha / reCAPTCHA / Cloudflare Turnstile / Arkose | STOP and ask. Never solve, never retry to dodge it, never use a solving service |
| phone number requested or SMS / voice verification | STOP and ask |
| terms of service or robots.txt that bar automated access, bots, or AI agents (the Dow Jones §9.4.1 shape) | STOP and ask; record the clause |
| a password field for a NEW password, or Google asking to re-enter the password / 2FA | STOP and ask |
| a checkbox that consents to marketing, data sharing or a paid add-on | leave unticked; if it is required, STOP and ask |
| identity documents, date of birth, address, tax id, employer, "accredited investor" questions | STOP and ask |
| the page leaves the task's hosts | STOP (close the tab) |
| any "post", "message", "invite contacts", "share", "connect your contacts / inbox" step | REFUSE |

Never: disguise automation, change the user agent, slow typing to look human, rotate accounts,
create more than one account per site, or retry after a refusal page.

## 4. What stays true whatever the owner decides

The reader stays read-only. `NEVER_HOSTS` stay. No payments, messages, emails or posts. A
sign-up is an owner-visible event (Telegram alert with the task record) and each new account is
listed in one ledger the owner can read and revoke.

## 5. Recommendation

Build it only when a named data source needs it and a free API key is not available: most of the
free sources in `vendor_tools_assessed_2026-09-29.md` issue keys by e-mail form, and a human doing
that once takes two minutes. The recommended first version is **"prepare, not submit"**: the agent
navigates, fills name and e-mail, takes the screenshot, and hands the owner the tab for the final
click. That removes most of the account risk and keeps every guard testable offline.
