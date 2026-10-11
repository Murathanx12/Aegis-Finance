"""Pure exact-endpoint Beta probability outcomes; no quote fetch or ledger IO.

Computed outcomes require external outcome review before learning. Original
expired forecasts are scored at their original formation, never reused as a
current forecast. Native price returns are not fills, P&L or total returns.
"""
from __future__ import annotations

from copy import deepcopy
import math

from backend.services import beta_v1_news_runtime as R

VERSION = "beta_news_outcomes/1"
MAX_ORIGINALS = 1000
LOG_FLOOR = 1e-12


def _seal(value):
    return {**value,"artifact_hash":R.digest(value)}


def verify(value):
    if value.get("artifact_hash") != R.digest({k:v for k,v in value.items() if k!="artifact_hash"}):
        raise R.RuntimeRefused("OUTCOME_HASH_DRIFT")


def original_row(original):
    """Re-admit complete original capture at its original forecast clock."""
    from backend.services import beta_v1_policy as P
    row = original["record"]
    admitted = R.normalize_reviewed(original["bundle"], original["capture"], original["numeric_review"],
        original["qualifications"], original["definitions"], made_at=row["forecast_at"])
    if (P.digest(admitted["candidate"]) != P.digest(row)
            or not admitted["admission"]["records"]
            or row["source_hash"] != original["bundle"].get("numeric_capture_hash", row["source_hash"])):
        raise R.RuntimeRefused("ORIGINAL_ADMISSION_UNAVAILABLE")
    return row


def score(original, quotes, quote_qualifications, *, cutoff):
    """Four externally qualified quotes, exact declared IDs/windows and basis."""
    from backend.services import beta_v1_policy as P
    try:
        row = original_row(original)
        now = R.utc(cutoff)
        if quotes is None:
            raise R.RuntimeRefused("QUOTE_ACCESS_UNAVAILABLE")
        if now < R.utc(row["label_end_at"]):
            return {"status":"NOT_YET_DUE","forecast_id":row["forecast_id"]}
        if len(quotes) != 4:
            raise R.RuntimeRefused("EXACT_ENDPOINT_QUOTES_UNAVAILABLE")
        identity = original["capture"]["binding"]["identity"]
        target = original["capture"]["binding"]["target"]
        benchmark_id, basis_id = target.get("benchmark_security_id"), target.get("price_basis_id")
        if not benchmark_id or not basis_id:
            raise R.RuntimeRefused("DECLARED_BENCHMARK_OR_BASIS_UNAVAILABLE")
        expected = {(identity["security_id"], row["ticker"], row[k]) for k in ("label_start_at","label_end_at")}
        expected |= {(benchmark_id, "SPY", row[k]) for k in ("label_start_at","label_end_at")}
        by_key, available, hashes = {}, [], []
        for quote in quotes:
            key = (quote.get("security_id"),quote.get("ticker"),quote.get("session_close_at"))
            qhash = P.digest(quote)
            receipt = quote_qualifications.get(qhash, {})
            if key not in expected or key in by_key:
                raise R.RuntimeRefused("QUOTE_IDENTITY_ENDPOINT_DUPLICATE_OR_MISMATCH")
            if (quote.get("price_basis") != row["price_basis"] or quote.get("cost_basis") != "GROSS"
                    or quote.get("price_basis_id") != basis_id
                    or receipt.get("decision") != "EXACT_ENDPOINT_ACCEPTED"
                    or receipt.get("independent") is not True or not receipt.get("reviewer")
                    or receipt.get("quote_sha256") != qhash
                    or receipt.get("source_hash") != quote.get("source_hash")
                    or not isinstance(quote.get("source_hash"),str) or len(quote["source_hash"]) != 64
                    or any(c not in "0123456789abcdef" for c in quote["source_hash"])
                    or not receipt.get("source_ref") or not receipt.get("qualification_reason")):
                raise R.RuntimeRefused("QUOTE_SOURCE_BASIS_REVIEW_UNAVAILABLE")
            price = quote.get("close")
            if type(price) not in (int,float) or not math.isfinite(price) or price <= 0:
                raise R.RuntimeRefused("FINITE_POSITIVE_QUOTE_UNAVAILABLE")
            close, observed, reviewed = (R.utc(v) for v in (quote["session_close_at"],quote["available_at"],receipt["reviewed_at"]))
            if not close <= observed <= reviewed <= now:
                raise R.RuntimeRefused("QUOTE_OR_REVIEW_AVAILABILITY_UNAVAILABLE")
            by_key[key] = price
            available.extend([observed,reviewed])
            hashes.append(qhash)
        start,end = row["label_start_at"],row["label_end_at"]
        sid = identity["security_id"]
        ret = by_key[(sid,row["ticker"],end)] / by_key[(sid,row["ticker"],start)]-1
        bench = by_key[(benchmark_id,"SPY",end)] / by_key[(benchmark_id,"SPY",start)]-1
        relative = ret-bench
        if not all(math.isfinite(v) for v in (ret,bench,relative)):
            raise R.RuntimeRefused("NONFINITE_PRICE_RETURN")
        y,p = int(relative>0),row["x"]
        logloss = -math.log(max(LOG_FLOOR,p if y else 1-p))
        grade_at = max(available).isoformat()
        graded = {**deepcopy(row),"y":y,"rel_return":relative,"outcome_at":grade_at}
        return _seal({"schema":VERSION,"status":"OUTCOME_EXTERNAL_REVIEW_REQUIRED",
            "forecast_id":row["forecast_id"],"original_record_hash":P.digest(row),
            "original_capture_hash":P.digest(original["capture"]),"original_forecast_at":row["forecast_at"],
            "original_probability":p,"security_id":sid,"benchmark_security_id":benchmark_id,
            "target_hash":P.digest(target),"quote_hashes":sorted(hashes),
            "quote_review_hashes":sorted(P.digest(quote_qualifications[h]) for h in hashes),
            "grade_available_at":grade_at,"scored_at":cutoff,"graded_record":graded,
            "realised_price_return":ret,"benchmark_price_return":bench,"gross_relative_price_return":relative,
            "benchmark_outperformance":bool(y),"probability_direction_correct":None if p==.5 else ((p>.5)==bool(y)),
            "brier":(p-y)**2,"log_loss":logloss,"log_probability_floor":LOG_FLOOR,
            "net_50bps_relative_diagnostic":relative-.005,"diagnostic_cost_only":True,
            "limitations":"Native price basis adjustment unknown; no fills/PnL/total return/portfolio cost authority",
            "learning_authority":False,"development_family":"beta_v1_news_probability_v1"})
    except (ValueError,TypeError,KeyError,OverflowError) as exc:
        allowed={"QUOTE_ACCESS_UNAVAILABLE","EXACT_ENDPOINT_QUOTES_UNAVAILABLE",
            "DECLARED_BENCHMARK_OR_BASIS_UNAVAILABLE","QUOTE_IDENTITY_ENDPOINT_DUPLICATE_OR_MISMATCH",
            "QUOTE_SOURCE_BASIS_REVIEW_UNAVAILABLE","FINITE_POSITIVE_QUOTE_UNAVAILABLE",
            "QUOTE_OR_REVIEW_AVAILABILITY_UNAVAILABLE","NONFINITE_PRICE_RETURN","ORIGINAL_ADMISSION_UNAVAILABLE"}
        reason=str(exc) if isinstance(exc,R.RuntimeRefused) and str(exc) in allowed else "EXACT_ORIGINAL_OR_ENDPOINT_EVIDENCE_UNAVAILABLE"
        return {"status":"UNAVAILABLE","reason":reason,
                "records":[],"learning_authority":False}


def catchup(originals, quote_sets, quote_qualifications, *, cutoff, existing=None):
    """Idempotent immutable grades; conflicting ID/root cohorts are quarantined."""
    from backend.services import beta_v1_policy as P
    if len(originals)>MAX_ORIGINALS:
        raise R.RuntimeRefused("OUTCOME_ROW_CAP")
    existing=existing or {}
    if not isinstance(existing,dict) or len(existing)+len(originals)>MAX_ORIGINALS:
        raise R.RuntimeRefused('OUTCOME_ROW_CAP')
    # Count/size before allocating deep copies; iterencode refuses incrementally.
    size=0
    import json
    for text in json.JSONEncoder(allow_nan=False).iterencode({'existing':existing,'incoming':originals}):
        size+=len(text.encode())
        if size>R.MAX_OUTPUT-R.PROOF_RESERVE:raise R.RuntimeRefused('OUTCOME_INPUT_CAP')
    saved=deepcopy(existing)
    for key,grade in saved.items():
        verify(grade)
        if grade.get("schema") != VERSION or grade.get("forecast_id") != key:
            raise R.RuntimeRefused("EXISTING_GRADE_IDENTITY_UNAVAILABLE")
    def root_key(row):
        return tuple(row.get(k) for k in ('component','task','horizon','objective_version','root_event'))
    groups,root_groups={},{}
    for key,grade in saved.items():
        prior=grade['graded_record']
        root_groups.setdefault(root_key(prior),set()).add(key)
    for original in originals:
        row=original["record"]
        groups.setdefault(row["forecast_id"],{})[P.digest(original)]=original
        root_groups.setdefault(root_key(row),set()).add(row['forecast_id'])
    blocked={ident for ids in root_groups.values() if len(ids)>1 for ident in ids}
    refused=[]
    for ident in sorted(groups):
        values=groups[ident]
        if len(values)!=1 or ident in blocked:
            refused.append({"forecast_id":ident,"reason":"CONFLICTING_ORIGINAL_ID_OR_ROOT_QUARANTINED"})
            continue
        original=next(iter(values.values()))
        if ident in saved:
            if saved[ident]["original_record_hash"]!=P.digest(original["record"]):
                refused.append({"forecast_id":ident,"reason":"IMMUTABLE_PRIOR_GRADE_ORIGINAL_CONFLICT"})
            continue
        outcome=score(original,quote_sets.get(ident),quote_qualifications,cutoff=cutoff)
        if outcome.get("status")=="OUTCOME_EXTERNAL_REVIEW_REQUIRED":
            saved[ident]=outcome
        else:
            refused.append({"forecast_id":ident,"status":outcome["status"],"reason":outcome.get("reason")})
    result={"schema":VERSION,"grades":saved,"refusals":refused,"learning_authority":False,
            "catalog_route":"PRIVATE_DEVELOPMENT_ONLY_NOT_LEGACY_CATALOG_REGISTRATION"}
    if len(R.encode(result))>R.MAX_OUTPUT-R.PROOF_RESERVE:
        raise R.RuntimeRefused("OUTCOME_OUTPUT_CAP")
    return result
