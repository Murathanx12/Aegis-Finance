"""Regressions for the observed caught-error/zero-forecast reporting failure."""
import json

from backend.services.forecast_receipt_metadata import forecast_metadata


def review(attempted=10, failed=10, written=0):
    return {
        "status": "ok",
        "belief_review": {
            "status": "ok", "attempted": attempted,
            "failed": failed, "written": written,
        },
    }


def test_all_attempts_failed_is_explicit_despite_returned_ok():
    result = forecast_metadata("arena", {"receipts": [review()]})
    assert (result["attempted"], result["failed"], result["written"]) == (10, 10, 0)
    assert result["status"] == "DEGRADED"
    assert result["zero_write_reason"] == "ALL_ATTEMPTS_FAILED"
    assert result["counts_complete"] is True


def test_partial_coverage_is_not_reported_as_all_books():
    result = forecast_metadata("arena", {
        "receipts": [review(), {"status": "already_marked"}],
    })
    assert result["written"] == 0
    assert result["counts_complete"] is False
    assert result["count_scope"] == "REPORTED_VALID_REVIEWS_ONLY"
    assert result["zero_write_reason"] == "ALL_REPORTED_ATTEMPTS_FAILED"


def test_absent_or_invalid_counts_remain_unknown():
    for row in (
        {"belief_review": {"status": "ok"}},
        review(attempted=True),
        review(failed=-1),
        review(attempted=1, failed=2),
    ):
        result = forecast_metadata("arena", {"receipts": [row]})
        assert result["written"] is None
        assert result["status"] == "UNAVAILABLE"
        assert result["unavailable_reason"] == "COUNTERS_UNAVAILABLE"


def test_why_lens_attempts_and_prediction_records_keep_their_scope():
    result = forecast_metadata("why_moved", {
        "lenses": [{"status": "ok"}, {"status": "degraded"}],
        "n_predictions_minted": 3,
    })
    assert (result["attempted"], result["failed"], result["written"]) == (2, 1, 3)
    assert result["count_scope"] == "RETURNED_LENSES_AND_MINTED_RECORDS"
    assert result["status"] == "DEGRADED"


def test_private_error_payload_never_enters_public_metadata():
    secret = "PRIVATE_ERROR_SENTINEL"
    result = forecast_metadata("arena", {
        "receipts": [{"belief_review": {
            "status": "error: " + secret, "prompt": secret, "posterior": secret,
        }}],
    })
    assert result["unavailable_reason"] == "REVIEW_EXCEPTION"
    assert secret not in json.dumps(result)
