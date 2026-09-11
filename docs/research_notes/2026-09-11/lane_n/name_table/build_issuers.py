"""Build issuers.csv skeleton for the 3,056-symbol universe.

No local company-name file was found under backend/data (grepped for
shortName/longName/issuer; only vocab files matched, not a symbol->name
table). Per the task instructions: pull yfinance info["shortName"] for a
200-name SAMPLE only (rate-limited, unofficial), and otherwise leave
primary_name blank with alias = ticker itself, so the gap is visible rather
than silently filled.
"""
import csv
import json
import time

UNIVERSE = r"C:\Users\mrthn\aegis-finance\backend\data\optimus\potential_universe\2026-09-02.jsonl"
OUT_CSV = r"C:\Users\mrthn\AppData\Local\Temp\claude\C--Users-mrthn-aegis-finance\89c0f226-6989-48c5-80c7-9dd6312631f8\scratchpad\lane_n\name_table\issuers.csv"
SAMPLE_LOG = r"C:\Users\mrthn\AppData\Local\Temp\claude\C--Users-mrthn-aegis-finance\89c0f226-6989-48c5-80c7-9dd6312631f8\scratchpad\lane_n\name_table\yfinance_sample_log.json"

rows = []
with open(UNIVERSE, encoding="utf-8") as f:
    for i, line in enumerate(f):
        row = json.loads(line)
        if i == 0 and "artefact" in row:
            continue
        sym = row.get("symbol")
        if not sym:
            continue
        ident = row.get("identity", {})
        exch = ident.get("exchange", "")
        rows.append({"symbol": sym, "exchange": exch})

print(f"universe symbols: {len(rows)}")

# 200-name sample: first 200 alphabetically (deterministic, reproducible)
SAMPLE_N = 200
sample_symbols = {r["symbol"] for r in rows[:SAMPLE_N]}

names = {}
sample_results = []
try:
    import yfinance as yf
    t_start = time.time()
    for idx, sym in enumerate(sorted(sample_symbols)):
        t0 = time.time()
        try:
            info = yf.Ticker(sym).info
            short = info.get("shortName") or info.get("longName") or ""
            names[sym] = short
            sample_results.append({"symbol": sym, "shortName": short, "status": "OK", "latency_s": round(time.time() - t0, 3)})
        except Exception as e:
            sample_results.append({"symbol": sym, "status": "EXC", "error": str(e), "latency_s": round(time.time() - t0, 3)})
        if idx % 25 == 0:
            print(f"...{idx}/{SAMPLE_N} elapsed={time.time() - t_start:.1f}s")
    total_elapsed = time.time() - t_start
    print(f"yfinance .info sample done: {len(names)}/{SAMPLE_N} in {total_elapsed:.1f}s "
          f"({total_elapsed / max(SAMPLE_N,1):.2f}s/name)")
except ImportError:
    print("yfinance not available")

with open(SAMPLE_LOG, "w", encoding="utf-8") as f:
    json.dump({"n_sampled": SAMPLE_N, "n_ok": len(names), "elapsed_s": round(total_elapsed, 1) if 'total_elapsed' in dir() else None,
               "results": sample_results}, f, indent=2, ensure_ascii=False)

COMMON_SUFFIXES = [
    " Inc.", " Inc", " Corporation", " Corp.", " Corp", " Ltd.", " Ltd",
    " PLC", " plc", " Co.", " Co", " Company", " Holdings", " Group",
    " Limited", " N.V.", " S.A.", " AG", " SE", " ADR", " American Depositary",
]

def strip_suffixes(name: str) -> str:
    n = name
    changed = True
    while changed:
        changed = False
        for suf in COMMON_SUFFIXES:
            if n.endswith(suf):
                n = n[: -len(suf)].strip().rstrip(",").strip()
                changed = True
    return n

with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["symbol", "primary_name", "aliases", "country", "is_adr"])
    for r in rows:
        sym = r["symbol"]
        exch = r["exchange"] or ""
        primary = names.get(sym, "")
        aliases = [sym]
        if primary:
            aliases.append(strip_suffixes(primary))
        alias_str = "|".join(dict.fromkeys(aliases))  # dedupe, keep order
        # country: crude derivation from exchange field; universe is US-listed
        # (Alpaca-tradable) so default US unless exchange string says otherwise.
        country = "US"
        if "HK" in exch.upper():
            country = "HK"
        elif exch.upper() in ("TSE", "TYO"):
            country = "JP"
        is_adr = ""  # left blank here; asia_adrs.csv is the authoritative ADR/dual-listing table
        w.writerow([sym, primary, alias_str, country, is_adr])

print(f"wrote {OUT_CSV}")
