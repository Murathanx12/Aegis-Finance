"""AST-only observability tests: provider, quote, cost and ledger paths are stubs."""
import __future__
import ast
import builtins
import json
import math
import threading
import unittest
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
NEW_KEYS = {"budget_reason_code", "no_wire"}
SUMMARY_KEYS = {"budget_refusal_reasons", "budget_refusal_no_wire"}


class Sandbox:
    def __init__(self, la_path, wd_path):
        self.effects = Counter()
        self.unexpected_imports = []
        self.response_error = None

        def create(**kwargs):
            self.effects["provider_stub"] += 1
            if self.response_error is not None:
                raise self.response_error
            raise AssertionError("test must declare a provider outcome")

        def quote(*args, **kwargs):
            self.effects["quote_stub"] += 1
            return {"reserved_units": 10_000_000}

        self.pb = SimpleNamespace(quote=quote, SCALE=1_000_000_000, BudgetRefused=RuntimeError)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        services = SimpleNamespace(provider_budget=self.pb, llm_telemetry=SimpleNamespace())
        language = SimpleNamespace(LANGUAGE_PIN="fixture")

        def imports(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "backend.services":
                return services
            if name == "backend.services.provider_budget":
                return self.pb
            if name == "backend.services.llm_language":
                return language
            self.unexpected_imports.append(name)
            raise AssertionError("unexpected application import")

        def cost(*args):
            self.effects["cost_stub"] += 1
            return "fixture_cost"

        self.ns = dict(
            __builtins__={**vars(builtins), "__import__": imports},
            Counter=Counter, math=math, threading=threading, time=SimpleNamespace(time=lambda: 0.0,
                                                                               perf_counter=lambda: 0.0),
            _config_mod=SimpleNamespace(MODEL_ROUTING_PROVIDERS={}, MODEL_ROUTING_MAX_TOKENS=700),
            _llm_cfg={}, _DEEPSEEK_MODEL="fixture_model", _DEEPSEEK_API_KEY=True,
            _get_openai_client=lambda: client, _acquire_call_budget=lambda: False,
            _spend_state={"breaker_until": 0.0}, _LANGUAGE_PIN="fixture",
            cost_status=cost, _record=lambda *a, **kw: self.effects.update(["record_stub"]),
            _is_billing_error=lambda e: False, _is_rate_limited=lambda e: False,
            _budgeted_deepseek_create=lambda *a, **kw: create(**kw),
        )
        self.native = "_budgeted_deepseek_create(" in Path(la_path).read_text(encoding="utf-8")
        self._load(la_path, {"_budget_refusal_metadata", "call_named"})
        self._load(wd_path, {"Meter", "BudgetExceeded"})

    def _load(self, path, names):
        tree = ast.parse(Path(path).read_bytes())
        nodes = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in names]
        module = ast.Module(body=nodes, type_ignores=[])
        exec(compile(ast.fix_missing_locations(module), str(path), "exec",
                     flags=__future__.annotations.compiler_flag), self.ns)

    def call(self, **kwargs):
        return self.ns["call_named"]("deepseek", "fixture system", "fixture user",
                                      purpose="fixture", max_tokens=100, **kwargs)

    def meter(self, response, budget=1.0):
        return self.ns["Meter"](budget, llm=lambda *a, **kw: dict(response))


class BudgetObservabilityTests(unittest.TestCase):
    # Private acceptance runner also sets these to the exact native candidate/preimage.
    source_pair = None
    baseline_pair = None

    def setUp(self):
        pair = self.source_pair or (ROOT / "backend/services/llm_analyzer.py",
                                    ROOT / "backend/services/world_digest.py")
        self.s = Sandbox(*pair)
        self.base = Sandbox(*self.baseline_pair) if self.baseline_pair else None

    def tearDown(self):
        self.assertEqual(self.s.unexpected_imports, [])
        if self.base:
            self.assertEqual(self.base.unexpected_imports, [])

    def test_controlled_refusal_taxonomy_and_block_redaction(self):
        f = self.s.ns["_budget_refusal_metadata"]
        cases = {
            "price authority requires official HTTPS DeepSeek endpoint": "endpoint_authority",
            "unpriced request model or invalid output bound": "request_contract",
            "unsupported non-text request": "request_contract",
            "only two plain text messages are reservation-qualified": "request_contract",
            "shared envelope absent/unreadable; explicit initialization required": "shared_envelope_unavailable",
            "shared incremental dollar cap would be exceeded": "shared_incremental_cap",
            "shared production daily call cap": "shared_production_cap",
            "shared envelope blocked: SECRET https://private.invalid/token": "shared_envelope_blocked",
        }
        for message, reason in cases.items():
            error = RuntimeError(message)
            error.no_wire = True
            self.assertEqual(f(error), {"budget_reason_code": reason, "no_wire": True})
            self.assertNotIn("SECRET", json.dumps(f(error)))

    def test_unknown_and_nonboolean_flags_never_claim_no_wire(self):
        f = self.s.ns["_budget_refusal_metadata"]
        for flag in (None, False, 1, "true", {}):
            error = RuntimeError("SECRET https://private.invalid/path")
            error.no_wire = flag
            self.assertEqual(f(error), {"budget_reason_code": "unknown_budget_refusal", "no_wire": None})
        error.no_wire = True
        self.assertEqual(f(error), {"budget_reason_code": "unknown_budget_refusal", "no_wire": True})
        self.assertEqual(f(gate={}), {"budget_reason_code": "unknown_budget_refusal", "no_wire": None})

    def test_diagnostic_stringification_failure_does_not_escape(self):
        class Error(RuntimeError):
            no_wire = True

            def __str__(self):
                raise ValueError("SECRET")
        self.assertEqual(self.s.ns["_budget_refusal_metadata"](Error()),
                         {"budget_reason_code": "unknown_budget_refusal", "no_wire": True})

    def test_existing_early_gates_only_add_metadata(self):
        for production, breaker, reason in ((True, 0.0, "production_gate"),
                                            (False, 10.0, "billing_breaker")):
            self.s.ns["_spend_state"]["breaker_until"] = breaker
            got = self.s.call(production_budget=production)
            self.assertEqual((got["status"], got["budget_reason_code"], got["no_wire"]),
                             ("BUDGET_REFUSED", reason, True))
            self.assertEqual(self.s.effects["provider_stub"], 0)
            self.assertEqual(self.s.effects["cost_stub"], 0)
            if self.base:
                self.base.ns["_spend_state"]["breaker_until"] = breaker
                old = self.base.call(production_budget=production)
                self.assertEqual({k: v for k, v in got.items() if k not in NEW_KEYS}, old)
                self.assertEqual(self.s.effects, self.base.effects)

    def test_native_existing_no_wire_return_only_adds_metadata(self):
        if not self.s.native:
            self.skipTest("W has no native shared-reservation adapter; exact R candidate is tested separately")
        error = RuntimeError("shared incremental dollar cap would be exceeded")
        error.no_wire = True
        self.s.response_error = error
        got = self.s.call(production_budget=False)
        self.assertEqual(got["status"], "BUDGET_REFUSED")
        self.assertEqual(got["budget_reason_code"], "shared_incremental_cap")
        self.assertIs(got["no_wire"], True)
        self.assertEqual(got["budget_charge_usd"], 0.0)
        if self.base:
            self.base.response_error = error
            old = self.base.call(production_budget=False)
            self.assertEqual({k: v for k, v in got.items() if k not in NEW_KEYS}, old)
            self.assertEqual(self.s.effects, self.base.effects)

    def test_wire_exception_behavior_unchanged(self):
        self.s.response_error = RuntimeError("fixture transport failure")
        got = self.s.call(production_budget=False)
        self.assertEqual(got["status"], "ERROR")
        self.assertFalse(NEW_KEYS.intersection(got))
        if self.base:
            self.base.response_error = self.s.response_error
            self.assertEqual(got, self.base.call(production_budget=False))
            self.assertEqual(self.s.effects, self.base.effects)

    def test_safe_summary_and_unknown_metadata(self):
        response = dict(status="BUDGET_REFUSED", ok=False, cost_usd=0.0,
                        budget_charge_usd=0.0, budget_reason_code={"SECRET": "https://private.invalid"},
                        no_wire="true", model="fixture_model")
        m = self.s.meter(response)
        self.assertIsNone(m.call("fixture", "fixture", purpose="fixture", max_tokens=100,
                                 stage="extract", reserve_usd=0.02))
        result = m.summary()
        self.assertEqual(result["budget_refusal_reasons"], {"unknown_budget_refusal": 1})
        self.assertEqual(result["budget_refusal_no_wire"], {"unknown": 1})
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertNotIn("private.invalid", json.dumps(result))
        if self.base:
            before = self.base.meter(response)
            before.call("fixture", "fixture", purpose="fixture", max_tokens=100,
                        stage="extract", reserve_usd=0.02)
            self.assertEqual({k: v for k, v in result.items() if k not in SUMMARY_KEYS}, before.summary())

    def test_concurrent_enum_counters(self):
        def response(system, user, **kwargs):
            return dict(status="BUDGET_REFUSED", ok=False, cost_usd=0.0, budget_charge_usd=0.0,
                        budget_reason_code="shared_envelope_blocked" if int(user) % 2 else "SECRET",
                        no_wire=True if int(user) % 2 else None)
        m = self.s.ns["Meter"](1.0, llm=response)
        with ThreadPoolExecutor(max_workers=2) as workers:
            list(workers.map(lambda i: m.call("fixture", str(i), purpose="fixture", max_tokens=100,
                                             stage="extract", reserve_usd=0.02), range(20)))
        self.assertEqual(m.summary()["budget_refusal_reasons"],
                         {"shared_envelope_blocked": 10, "unknown_budget_refusal": 10})
        self.assertEqual(m.summary()["budget_refusal_no_wire"], {"true": 10, "unknown": 10})
        self.assertEqual(m.calls, 20)
        self.assertEqual(m.spent, 0.0)

    def test_non_refusal_and_explicit_wire_false(self):
        m = self.s.meter(dict(status="ERROR", ok=False, cost_usd=0.02,
                             budget_reason_code="SECRET", no_wire=True))
        m.call("fixture", "fixture", purpose="fixture", max_tokens=100, stage="extract")
        self.assertEqual(m.summary()["budget_refusal_reasons"], {})
        self.assertEqual(m.spent, 0.02)
        m = self.s.meter(dict(status="BUDGET_REFUSED", ok=False, cost_usd=0.0, budget_charge_usd=0.0,
                             budget_reason_code="billing_breaker", no_wire=False))
        m.call("fixture", "fixture", purpose="fixture", max_tokens=100, stage="extract")
        self.assertEqual(m.summary()["budget_refusal_no_wire"], {"false": 1})

    def test_local_caps_refuse_before_callback(self):
        for budget, cap in ((0.01, None), (1.0, 0.01)):
            called = []
            def forbidden(*args, **kwargs):
                called.append(True)
                raise AssertionError("callback forbidden")
            m = self.s.ns["Meter"](budget, llm=forbidden)
            with self.assertRaises(self.s.ns["BudgetExceeded"]):
                m.call("fixture", "fixture", purpose="fixture", max_tokens=100, stage="extract",
                       reserve_usd=0.02, stage_cap=cap)
            self.assertEqual(called, [])  # Outside the collector, cannot be masked.
            self.assertEqual(m.calls, 0)
            self.assertEqual(m.summary()["budget_refusal_reasons"], {})

    def test_unknown_charge_retention_unchanged(self):
        if not self.s.native:
            self.skipTest("Native reservation retention exists only in the separate R candidate")
        m = self.s.meter(dict(status="ERROR", ok=False, cost_usd=None))
        m.call("fixture", "fixture", purpose="fixture", max_tokens=100, stage="extract",
               reserve_usd=0.025)
        self.assertEqual(m.spent, 0.025)
        self.assertEqual(m.unpriced, 1)
        if self.base:
            old = self.base.meter(dict(status="ERROR", ok=False, cost_usd=None))
            old.call("fixture", "fixture", purpose="fixture", max_tokens=100, stage="extract",
                     reserve_usd=0.025)
            self.assertEqual({k: v for k, v in m.summary().items() if k not in SUMMARY_KEYS}, old.summary())
        callbacks = []

        def unknown_dispatch(*args, **kwargs):
            callbacks.append(True)
            raise RuntimeError("fixture unknown dispatch outcome")

        m = self.s.ns["Meter"](1.0, llm=unknown_dispatch)
        with self.assertRaisesRegex(RuntimeError, "fixture unknown dispatch outcome"):
            m.call("fixture", "fixture", purpose="fixture", max_tokens=100,
                   stage="extract", reserve_usd=0.025)
        self.assertEqual(callbacks, [True])
        self.assertEqual((m.spent, m.calls, m.failed, m.unpriced), (0.025, 1, 1, 1))
        self.assertEqual(m.summary()["budget_refusal_reasons"], {})
        if self.base:
            old = self.base.ns["Meter"](1.0, llm=unknown_dispatch)
            with self.assertRaises(RuntimeError):
                old.call("fixture", "fixture", purpose="fixture", max_tokens=100,
                         stage="extract", reserve_usd=0.025)
            self.assertEqual({k: v for k, v in m.summary().items() if k not in SUMMARY_KEYS}, old.summary())


if __name__ == "__main__":
    unittest.main()
