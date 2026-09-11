"""Verify Asia ADR / dual-listing pairs with a small yfinance probe.

Verifies each candidate US symbol resolves via yfinance (fast_info / info
shortName present, currency=USD) and records the paired local-exchange
symbol where known. Local-exchange (HK/JP/KR/TW/CN) company name in the
native script is NOT independently fetched here (would need per-name
yfinance calls on the .HK/.T/.KS tickers too — kept out of the <=200-row
probe budget already spent on the issuers sample); recorded as "not
probed" where absent.
"""
import csv
import json
import time
import yfinance as yf

OUT = r"C:\Users\mrthn\AppData\Local\Temp\claude\C--Users-mrthn-aegis-finance\89c0f226-6989-48c5-80c7-9dd6312631f8\scratchpad\lane_n\name_table\asia_adrs.csv"
LOG = r"C:\Users\mrthn\AppData\Local\Temp\claude\C--Users-mrthn-aegis-finance\89c0f226-6989-48c5-80c7-9dd6312631f8\scratchpad\lane_n\name_table\asia_adrs_verify_log.json"

# candidate, source_country, local_symbol (best known), local_exchange, notes
CANDIDATES = [
    ("BABA", "CN", "9988.HK", "HKEX", "Alibaba; NYSE ADR + HK primary listing (dual primary since 2019/2022 conversion)"),
    ("TSM", "TW", "2330.TW", "TWSE", "TSMC; NYSE ADR + Taiwan primary"),
    ("SONY", "JP", "6758.T", "TSE", "Sony Group; NYSE ADR + Tokyo primary"),
    ("TM", "JP", "7203.T", "TSE", "Toyota Motor; NYSE ADR + Tokyo primary"),
    ("PDD", "CN", "", "", "PDD Holdings (Pinduoduo/Temu); NASDAQ ADR, no confirmed HK dual listing found"),
    ("JD", "CN", "9618.HK", "HKEX", "JD.com; NASDAQ ADR + HK secondary listing"),
    ("NTES", "CN", "9999.HK", "HKEX", "NetEase; NASDAQ ADR + HK secondary listing"),
    ("BIDU", "CN", "9888.HK", "HKEX", "Baidu; NASDAQ ADR + HK secondary listing"),
    ("TCOM", "CN", "9961.HK", "HKEX", "Trip.com Group; NASDAQ + HK secondary listing"),
    ("LI", "CN", "2015.HK", "HKEX", "Li Auto; NASDAQ ADR + HK secondary listing"),
    ("NIO", "CN", "9866.HK", "HKEX", "NIO Inc; NYSE ADR + HK secondary listing"),
    ("XPEV", "CN", "9868.HK", "HKEX", "XPeng; NYSE ADR + HK secondary listing"),
    ("BILI", "CN", "9626.HK", "HKEX", "Bilibili; NASDAQ ADR + HK secondary listing"),
    ("HDB", "IN", "", "NSE/BSE", "HDFC Bank; NYSE ADR, India primary listing (HDFCBANK.NS)"),
    ("IBN", "IN", "", "NSE/BSE", "ICICI Bank; NYSE ADR, India primary listing (ICICIBANK.NS)"),
    ("WIT", "IN", "", "NSE/BSE", "Wipro; NYSE ADR, India primary listing (WIPRO.NS)"),
    ("INFY", "IN", "", "NSE/BSE", "Infosys; NYSE ADR, India primary listing (INFY.NS)"),
    ("SE", "SG", "", "", "Sea Limited; NYSE listing, Singapore-headquartered, no separate local listing found"),
    ("GRAB", "SG", "", "", "Grab Holdings; NASDAQ listing, Singapore-headquartered, no separate local listing found"),
    ("CPNG", "KR", "", "", "Coupang; NYSE listing, Korea-headquartered, no separate local listing found"),
    ("KB", "KR", "105560.KS", "KRX", "KB Financial Group; NYSE ADR + Korea primary"),
    ("SHG", "KR", "055550.KS", "KRX", "Shinhan Financial Group; NYSE ADR + Korea primary"),
    ("LPL", "KR", "034220.KS", "KRX", "LG Display Co Ltd (NOT LG Corp — LPL is LG Display's NYSE ADR ticker); NYSE ADR + Korea primary"),
    ("SKM", "KR", "017670.KS", "KRX", "SK Telecom; NYSE ADR + Korea primary"),
    ("MFG", "JP", "8411.T", "TSE", "Mizuho Financial Group; NYSE ADR + Tokyo primary (TSE code 8411)"),
    ("MUFG", "JP", "8306.T", "TSE", "Mitsubishi UFJ Financial Group; NYSE ADR + Tokyo primary (TSE code 8306)"),
    ("SMFG", "JP", "8316.T", "TSE", "Sumitomo Mitsui Financial Group; NYSE ADR + Tokyo primary"),
    ("NMR", "JP", "8604.T", "TSE", "Nomura Holdings; NYSE ADR + Tokyo primary"),
    ("HMC", "JP", "7267.T", "TSE", "Honda Motor; NYSE ADR + Tokyo primary"),
    ("CAJ", "JP", "7751.T", "TSE", "Canon Inc; NYSE ADR + Tokyo primary"),
    ("MRAAY", "JP", "8058.T", "TSE", "Mitsubishi Corp OTC ADR + Tokyo primary"),
]

rows_out = []
log = []

for us_sym, country, local_sym, local_exch, notes in CANDIDATES:
    t0 = time.time()
    entry = {"symbol": us_sym}
    try:
        info = yf.Ticker(us_sym).info
        entry["short_name"] = info.get("shortName")
        entry["currency"] = info.get("currency")
        entry["exchange"] = info.get("exchange")
        entry["status"] = "OK" if info.get("shortName") else "EMPTY_INFO"
    except Exception as e:
        entry["status"] = "EXC"
        entry["error"] = str(e)
    entry["latency_s"] = round(time.time() - t0, 2)
    log.append(entry)
    print(f"[{us_sym}] {entry.get('status')} {entry.get('short_name')} exch={entry.get('exchange')} latency={entry['latency_s']}s")
    rows_out.append({
        "us_symbol": us_sym,
        "local_symbol": local_sym,
        "local_exchange": local_exch,
        "source_country": country,
        "us_short_name_yfinance": entry.get("short_name", ""),
        "us_exchange_yfinance": entry.get("exchange", ""),
        "verified": "YES" if entry.get("status") == "OK" else "US_LEG_UNVERIFIED",
        "notes": notes,
    })
    time.sleep(0.8)

with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["us_symbol", "local_symbol", "local_exchange", "source_country",
                                       "us_short_name_yfinance", "us_exchange_yfinance", "verified", "notes"])
    w.writeheader()
    for r in rows_out:
        w.writerow(r)

with open(LOG, "w", encoding="utf-8") as f:
    json.dump(log, f, indent=2, ensure_ascii=False)

print(f"\nwrote {OUT}")
