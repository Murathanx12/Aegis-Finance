"""Sign OpenClaw's browser in from `.env` — without the password meeting a model.

MURAT, 2026-09-22
=================
    "give open claw the login information everytime so it can login from the
     env file"

The obvious way to do that is to put the account and password into the agent's
prompt and let it type them. **Do not do that.** A prompt is sent to the model
provider, so the password would travel to DeepSeek's API and sit in whatever
request logs live at the other end, for every login, forever.

This script does the same job with the credential never leaving the machine:

    .env  ->  a temp JSON file  ->  `openclaw browser fill --fields-file`  ->  the page

`openclaw browser fill` takes a file precisely so secrets do not have to go on a
command line (where they would land in the shell history and in every process
listing). The temp file is written with the narrowest permissions the OS allows
and deleted in a `finally`, on every path.

    python -m scripts.openclaw_login --site reddit
    python -m scripts.openclaw_login --site google
    python -m scripts.openclaw_login --site reddit --submit

WHAT IT WILL NOT DO
===================
* It does not solve a CAPTCHA or a 2FA challenge, and it does not pretend to:
  if the page asks for one it stops and says so, leaving the window open for
  Murat. An agent that works around a human-verification step is doing the one
  thing that step exists to prevent.
* It does not create accounts. Automated signup is against the terms of every
  site here, and the account in `.env` already exists.
* It never touches a brokerage, a bank, or anything that can move money. The
  allowlist below is the whole set of sites it knows how to sign into.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import types
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                         # noqa: E402,F401
from backend.services import openclaw_client as OC         # noqa: E402

logger = logging.getLogger("openclaw_login")

ACC_ENV = "OPENCLAW_ACC"
PASS_ENV = "OPENCLAW_Pass"

#: The only sites this will sign into. Adding one is a deliberate edit, and
#: nothing that holds money is eligible: brokerage stays on the API, where an
#: order has a client_order_id and a receipt.
#: Fields are matched by their ACCESSIBLE LABEL in a fresh snapshot, because
#: `browser fill` addresses elements by `ref` and a ref is only valid for the
#: snapshot that produced it. CSS selectors are not accepted, and a ref cached
#: from an earlier run points at nothing. So: snapshot, match, fill, in one pass.
#:
#: The label patterns are deliberately loose and case-insensitive -- the agent's
#: Chrome renders Reddit in whatever locale the profile carries (it came up in
#: Indonesian on 2026-09-22), so matching English chrome text exactly would
#: break on a language change nobody made on purpose.
SITES: dict[str, dict] = {
    "google": {
        "url": "https://accounts.google.com/signin/v2/identifier",
        "steps": [
            {"fields": [{"match": r"email|e-mail|phone|telepon", "value": "{acc}"}],
             "then_click": r"next|berikutnya|lanjut"},
            {"fields": [{"match": r"password|sandi|kata sandi", "value": "{pw}"}],
             "then_click": r"next|berikutnya|lanjut"},
        ],
        "note": "Google is two-step and often adds a device challenge; finish "
                "that by hand.",
    },
    "reddit": {
        "url": "https://www.reddit.com/login/",
        "steps": [
            {"fields": [
                {"match": r"email or username|username|nama pengguna", "value": "{acc}"},
                {"match": r"^password$|sandi", "value": "{pw}"},
            ], "then_click": r"log in|masuk"},
        ],
        "note": "Reddit blocks unauthenticated .json fetches; a signed-in "
                "session is what makes its public data readable.",
    },
}

#: `- textbox "Email or username" [ref=e95]`
_SNAP = re.compile(r'-\s*(textbox|combobox)\s+"([^"]+)"\s+\[ref=(e\d+)\]', re.I)
_BTN = re.compile(r'-\s*button\s+"([^"]+)"\s+\[ref=(e\d+)\]', re.I)


def snapshot() -> str:
    r = _openclaw("browser", "snapshot", timeout=180)
    return r.stdout or r.stderr or ""


def find_field(snap: str, pattern: str) -> str | None:
    """The ref of the first textbox whose label matches. None if absent."""
    rx = re.compile(pattern, re.I)
    for _kind, label, ref in _SNAP.findall(snap):
        if rx.search(label):
            return ref
    return None


def find_button(snap: str, pattern: str) -> str | None:
    rx = re.compile(pattern, re.I)
    for label, ref in _BTN.findall(snap):
        if rx.search(label):
            return ref
    return None


def looks_challenged(snap: str) -> str | None:
    """A human-verification step. We stop here rather than work around it."""
    for needle, what in (("captcha", "a CAPTCHA"),
                         ("verify you", "a human-verification step"),
                         ("two-factor", "2FA"), ("2-step", "2-step verification"),
                         ("verification code", "a verification code")):
        if needle in snap.lower():
            return what
    return None

BANNED = ("alpaca", "bank", "paypal", "stripe", "coinbase", "binance",
          "interactive", "schwab", "fidelity")


def credentials() -> tuple[str, str]:
    acc, pw = os.environ.get(ACC_ENV), os.environ.get(PASS_ENV)
    if not acc or not pw:
        raise SystemExit(
            f"REFUSED: set {ACC_ENV} and {PASS_ENV} in .env. "
            f"Present: {ACC_ENV}={'yes' if acc else 'NO'}, "
            f"{PASS_ENV}={'yes' if pw else 'NO'}")
    return acc, pw


def _openclaw(*args: str, timeout: float = 120.0):
    """Routed through `openclaw_client` so the PROFILE is named on every call.

    The first version shelled out to a bare `openclaw browser ...`, which used
    whatever `browser.defaultProfile` happened to be. That default moved four
    times in one afternoon. A browser profile is logged-in account access; it is
    not something to leave to a default.
    """
    assert args and args[0] == "browser", f"only browser verbs here, got {args!r}"
    verb, rest = args[1], [a for a in args[2:]]
    url = rest.pop() if rest and rest[-1].lower().startswith("http") else None
    r = OC.browser(verb, *rest, url=url, timeout=timeout)
    return types.SimpleNamespace(returncode=r["rc"], stdout=r["stdout"],
                                 stderr=r["stderr"])


def login(site: str, *, submit: bool = False) -> dict:
    if site not in SITES:
        raise SystemExit(f"REFUSED: unknown site {site!r}. Known: {sorted(SITES)}")
    spec = SITES[site]
    if any(b in spec["url"].lower() for b in BANNED):
        raise SystemExit(f"REFUSED: {site} looks money-adjacent; not via a browser agent.")

    acc, pw = credentials()
    out: dict = {"site": site, "url": spec["url"], "account": acc,
                 "steps": [], "note": spec.get("note")}

    r = _openclaw("browser", "open", spec["url"])
    out["opened"] = (r.stdout or r.stderr).strip()[:200]

    for i, step in enumerate(spec["steps"], start=1):
        snap = snapshot()
        challenge = looks_challenged(snap)
        if challenge:
            out["steps"].append({"step": i, "stopped": challenge})
            out["challenge"] = (
                f"The page is asking for {challenge}. This script does not "
                f"defeat human-verification steps, by design — finish it in the "
                f"open window.")
            return out
        fields = []
        for f in step["fields"]:
            ref = find_field(snap, f["match"])
            if not ref:
                out["steps"].append({"step": i, "missing_field": f["match"],
                                     "why": "no textbox on the page matched"})
                return out
            fields.append({"ref": ref, "value": f["value"].format(acc=acc, pw=pw)})
        fd, tmp = tempfile.mkstemp(suffix=".json", prefix="ocl_")
        try:
            os.write(fd, json.dumps(fields).encode())
            os.close(fd)
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            r = _openclaw("browser", "fill", "--fields-file", tmp)
            step_out = {"step": i,
                        "filled_refs": [f["ref"] for f in fields],
                        "rc": r.returncode,
                        "detail": (r.stdout or r.stderr).strip()[:300]}
        finally:
            # every path, including an exception inside `fill`
            try:
                os.unlink(tmp)
            except OSError:
                pass
        if submit and step.get("then_click"):
            btn = find_button(snapshot(), step["then_click"])
            if btn:
                c = _openclaw("browser", "click", btn)
                step_out["clicked"] = {"ref": btn,
                                       "detail": (c.stdout or c.stderr).strip()[:150]}
            else:
                step_out["clicked"] = {"ref": None,
                                       "detail": f"no button matched {step['then_click']!r}"}
        out["steps"].append(step_out)

    out["next"] = (
        "The window is open on the agent's own Chrome profile. If the page is "
        "asking for a CAPTCHA, a code or a device confirmation, finish it by "
        "hand — this script does not defeat human-verification steps, by design. "
        "Once signed in, the session persists in the managed profile and every "
        "later agent run reuses it.")
    return out


SIGNED_OUT = re.compile(r"(log ?in|sign ?in|sign ?up|masuk|daftar)", re.I)


def check(site: str) -> dict:
    """Is the persisted session still good? The night runner's question.

    Returns LOGIN_REQUIRED rather than attempting a login: deciding to re-auth
    is a human's call, because a wrong guess costs the account.
    """
    spec = SITES[site]
    OC.browser("open", url=spec["url"].replace("/login/", "/").replace("/signin/v2/identifier", "/"))
    snap = snapshot()
    challenged = looks_challenged(snap)
    signed_out = bool(SIGNED_OUT.search(snap))
    return {
        "site": site,
        "state": ("CHALLENGE" if challenged else
                  "LOGIN_REQUIRED" if signed_out else "SESSION_OK"),
        "challenge": challenged,
        "profile": OC.profile(),
        "detail": ("a human-verification step is on screen" if challenged else
                   "login/signup controls are visible, so the cookie is gone"
                   if signed_out else
                   "no login controls visible; the persisted session is holding"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="report SESSION_OK / LOGIN_REQUIRED / CHALLENGE and exit")
    ap.add_argument("--site", default="reddit", choices=sorted(SITES))
    ap.add_argument("--submit", action="store_true",
                    help="also click the submit button after filling")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if a.check:
        print(json.dumps(check(a.site), indent=1))
        return 0
    res = login(a.site, submit=a.submit)
    # the password is never in `res`; only selectors and outcomes are
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
