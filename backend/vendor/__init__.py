"""Third-party / cross-repo source kept VERBATIM, never edited here.

`backend/vendor/aat/alpha/` is a byte-identical mirror of two modules from the
EXECUTION repo (`aegis-alpha-terminal`): `alpha/human.py` (the `Thesis` schema)
and `alpha/brains/base.py` (the `Forecast` it returns). They are copied rather
than re-implemented because H2 says "reuse the existing schema VERBATIM, do not
invent a second one", and a second copy of a validation rule is how two repos
start refusing different things while both claim to enforce one contract.

WHY A COPY AND NOT AN IMPORT
============================
The website backend runs in a container that has never seen the execution repo,
and `sys.path`-ing into it would make `import alpha.brains` reachable from a
request handler -- the same package that owns the broker client. The mirror is
therefore the ONLY schema source at runtime (`backend/services/human_thesis.py`
loads it by path), and `backend/tests/test_human_thesis.py::TestSchemaIsVerbatim`
hashes it against the execution repo when that repo is on the machine and SKIPS
with a named reason when it is not. A skip is not a pass, and the test says so.

The two `__init__.py` files under `aat/alpha/` are EMPTY STUBS written here, not
copies: the real `alpha/brains/__init__.py` imports every brain in the fleet, and
importing those to validate a dataclass would drag a broker client into a
read-only web process. That is the one deliberate difference and it is asserted
in the test rather than left to this docstring.

NOTHING under `backend/vendor/` is reachable from a router by static import; it
is classified in `backend.services.signal_reachability.CLASSIFIED`.
"""
