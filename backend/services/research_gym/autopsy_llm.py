"""Ask Optimus to perform the autopsy, and refuse anything that is not testable.

WHAT THE MODEL IS AND IS NOT ALLOWED TO DO
==========================================
It is allowed to **see the outcome**. That is what an autopsy is, and pretending
otherwise would produce a forecast instead of a dissection.

It is not allowed to hand back a paragraph. The reply must populate the
`Autopsy` schema, whose constructor refuses a mechanism with no declared
unaffected states, no falsifier, no rival explanation, or a precursor that does
not compile. So a reply that reads beautifully and predicts nothing is rejected
by the type rather than by a reviewer's patience at the end of a long session.

The division of labour this project has settled on: **the LLM proposes meaning,
the market supplies the weights, Aegis judges truth.** Here that is literal —
the model writes the mechanism and the precursor; `adjudicate()` runs the
precursor on episodes the model never saw and reports what happened.

THE TOKEN CEILING IS NOT A DEFAULT HERE
=======================================
`llm_research.ask` defaults to `max_tokens=2000`. IIF-1's Night 1 was voided by
exactly that kind of number: on a reasoning model the ceiling bounds THINKING
PLUS answer, so a request for a large structured object comes back EMPTY rather
than short, and the cause is invisible in the reply. The autopsy schema is large
and the model is `deepseek-chat`, so the ceiling is raised deliberately here and
`finish_reason` is checked on the way back.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from backend.services.research_gym import autopsy as AU
from backend.services.research_gym.autopsy import (Autopsy, AutopsyRefused,
                                                   PrecursorRefused,
                                                   compile_precursor)

#: Raised well above the reply's true size. See the module docstring: the cost
#: of a ceiling that is too high is a few tenths of a cent; the cost of one that
#: is too low is a night that reports "the model said nothing".
MAX_TOKENS = 12_000

SCHEMA_HINT = """
Reply with ONE json object and nothing else. Every field is required.

{
  "contemporaneous_evidence": ["facts knowable AT the decision timestamp"],
  "post_outcome_evidence":    ["facts knowable ONLY after the outcome"],
  "failed_assumption":        "the belief that turned out to be wrong",
  "proposed_mechanism":       "why this is repeatable, not one bad afternoon",
  "executable_precursor":     {"all": [{"feature": "vix", "op": ">=",
                                        "value": 35}]},
  "expected_affected_states":   ["states where this must show up"],
  "expected_unaffected_states": ["states where this must be ABSENT"],
  "falsifier":                "the observation that would kill this",
  "alternative_explanation":  "the most credible rival account",
  "proposed_action":          "one policy name from the menu given above",
  "default_action":           "hold"
}

RULES THE REPLY MUST OBEY OR IT IS DISCARDED
- `executable_precursor` may ONLY read features from the TRANSFERABLE
  VOCABULARY listed below — not every field shown under STATE. Features
  outside it exist on this episode but NOT on the out-of-sample episodes the
  rule will be tested against, so a precursor using one is untestable by
  construction and is discarded. Operators: > >= < <= == != in not_in,
  combined with all / any / not.
  It may NOT read the outcome, the realised return, or the failure mode.
- `proposed_action` must DIFFER from `default_action`. A mechanism whose
  proposal equals its control has an edge of exactly zero on every slice.
- `expected_unaffected_states` may not be empty and may not overlap
  `expected_affected_states`. A mechanism that predicts every state predicts
  nothing.
- Anything you knew only because you were shown the outcome belongs in
  `post_outcome_evidence`, never in `contemporaneous_evidence`.
"""


class AutopsyReplyUnusable(RuntimeError):
    """The reply could not become a testable autopsy, and why."""


def build_prompt(episode, surface, *, base_rate=None) -> str:
    """Everything the model needs and nothing it must not infer from framing."""
    state_keys = sorted(episode.state)
    top = surface.ranked()[:5]
    worst = surface.ranked()[-3:]
    taken = surface.taken

    lines = [
        "You are performing an AUTOPSY on one resolved portfolio decision.",
        "You may see the outcome. That is the point. Your job is to say what "
        "would have to be true about the WORLD for this to be a repeatable "
        "mistake rather than one bad afternoon, and to state it so it can be "
        "tested on decisions you have not seen.",
        "",
        f"DECISION      {episode.decision_ts}  {episode.security}",
        f"ACTION TAKEN  {episode.action}  "
        f"(exposure {episode.exposure_before} -> {episode.exposure_after})",
        f"STATED REASON {episode.stated_reason}",
        "",
        "STATE at the decision (context — not all of it is usable in a rule):",
    ]
    for k in state_keys:
        mark = "  [transferable]" if k in AU.TRANSFERABLE_FEATURES else ""
        lines.append(f"  {k} = {episode.state[k]!r}{mark}")
    usable = sorted(set(state_keys) & set(AU.TRANSFERABLE_FEATURES))
    lines += [
        "",
        "TRANSFERABLE VOCABULARY — the precursor may read ONLY these, because "
        "they are the only fields the out-of-sample corpus also carries:",
        "  " + ", ".join(usable) if usable else
        "  (none — do not propose a precursor)",
    ]
    lines += [
        "",
        f"BELIEFS       P(up)={episode.beliefs.p_up} over "
        f"{episode.beliefs.horizon_days}d",
        f"OUTCOME       realised "
        f"{episode.outcome.realised_return_pct:+.2f}% over "
        f"{episode.outcome.horizon_days}d",
        "",
        "COUNTERFACTUALS — what every alternative action returned, net of cost:",
    ]
    for r in top:
        lines.append(f"  {r.name:<32s} {r.net_return_pct:+8.2f}%")
    lines.append("  ...")
    for r in worst:
        lines.append(f"  {r.name:<32s} {r.net_return_pct:+8.2f}%")
    if taken is not None:
        lines.append(f"  ACTION TAKEN ({taken.name}) returned "
                     f"{taken.net_return_pct:+.2f}%")

    # The denominator is given TO the model, because a model handed only
    # "regret +26pp" will write a mechanism explaining a number that is half
    # denominator. This is G1 propagated into the prompt.
    if episode.regret:
        lines += [
            "",
            "REGRET, IN THREE DENOMINATORS (do not treat the first as skill):",
            f"  vs ex-post best      "
            f"{episode.regret.get('vs_ex_post_best_pp')} pp  "
            f"(UPPER BOUND — a maximum over the menu; a blameless decision "
            f"scores large positive values here)",
            f"  vs a fixed HOLD      "
            f"{episode.regret.get('vs_fixed_default_pp')} pp  (unbiased)",
            f"  excess over the null "
            f"{episode.regret.get('excess_vs_matched_null_pp')} pp  "
            f"(what a same-state same-action decision with no skill scores has "
            f"already been subtracted)",
        ]
    if base_rate is not None and base_rate.p_up is not None:
        n_eff = ("unknown" if base_rate.n_effective is None
                 else f"{base_rate.n_effective:.1f}")
        lines += [
            "",
            f"BASE RATE for {base_rate.state_key}: P(up) "
            f"{base_rate.p_up:.3f}, mean {base_rate.horizon_days}d "
            f"{base_rate.mean_forward_return_pct:+.2f}%, n={base_rate.n} but "
            f"n_effective={n_eff} (overlapping windows). Treat this as weak "
            f"evidence about what usually followed, not as a measurement.",
        ]
    lines += [
        "",
        "A mechanism that only explains THIS episode will be tested on other "
        "securities, periods and crises and will fail. Propose something that "
        "could survive that.",
    ]
    return "\n".join(lines)


def parse_reply(text: str, episode_id: str, *, author: str = "") -> Autopsy:
    """Reply -> `Autopsy`, or a refusal that names what was wrong.

    Never repairs the reply. A parser that fills in a missing falsifier or
    drops an uncompilable precursor produces an autopsy the model did not
    write, and the resulting mechanism is then attributed to a reasoning
    process that never happened.
    """
    if not text or not text.strip():
        raise AutopsyReplyUnusable(
            "empty reply — on a reasoning model this is what a token ceiling "
            "looks like, not what a refusal looks like; check finish_reason")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise AutopsyReplyUnusable("no json object in the reply")
    try:
        raw = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        raise AutopsyReplyUnusable(f"unparseable json: {exc}") from exc

    try:
        return Autopsy(
            episode_id=episode_id,
            contemporaneous_evidence=list(
                raw.get("contemporaneous_evidence") or []),
            post_outcome_evidence=list(raw.get("post_outcome_evidence") or []),
            failed_assumption=str(raw.get("failed_assumption") or ""),
            proposed_mechanism=str(raw.get("proposed_mechanism") or ""),
            executable_precursor=raw.get("executable_precursor") or {},
            expected_affected_states=list(
                raw.get("expected_affected_states") or []),
            expected_unaffected_states=list(
                raw.get("expected_unaffected_states") or []),
            falsifier=str(raw.get("falsifier") or ""),
            alternative_explanation=str(
                raw.get("alternative_explanation") or ""),
            proposed_action=str(raw.get("proposed_action") or "hold"),
            default_action=str(raw.get("default_action") or "hold"),
            author=author)
    except (AutopsyRefused, PrecursorRefused) as exc:
        raise AutopsyReplyUnusable(f"{type(exc).__name__}: {exc}") from exc


def propose(episode, surface, *, base_rate=None,
            ask: Callable[..., dict] | None = None,
            model: str = "deepseek-chat") -> dict:
    """One ledgered autopsy proposal. Returns the autopsy AND the drop reason.

    Returns rather than raises on an unusable reply, because "the model was
    asked and produced nothing testable" is a RESULT — it belongs in the
    mechanism-yield count, and an exception would leave it out of the
    denominator.
    """
    if ask is None:
        from backend.services.llm_research import ask as _ask
        ask = _ask

    prompt = build_prompt(episode, surface, base_rate=base_rate)
    out: dict[str, Any] = {"episode_id": episode.episode_id, "autopsy": None,
                           "drop_reason": "", "call": None}
    try:
        res = ask(prompt, purpose="research_gym_autopsy", model=model,
                  temperature=0.0, max_tokens=MAX_TOKENS,
                  schema_hint=SCHEMA_HINT)
    except Exception as exc:                                     # noqa: BLE001
        out["drop_reason"] = f"call_failed: {type(exc).__name__}: {exc}"
        return out

    out["call"] = res.get("call")
    if res.get("truncated"):
        # Named, not inferred. This is the failure mode that cost a night.
        out["drop_reason"] = (
            f"reply_truncated_at_token_ceiling (max_tokens={MAX_TOKENS}); the "
            f"ceiling bounds thinking plus answer on a reasoning model")
        return out
    try:
        out["autopsy"] = parse_reply(res.get("text") or "", episode.episode_id,
                                     author=model)
    except AutopsyReplyUnusable as exc:
        out["drop_reason"] = f"reply_not_testable: {exc}"
    return out
