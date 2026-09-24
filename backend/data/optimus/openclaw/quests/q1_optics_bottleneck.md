You are gathering EVIDENCE, not opinions. You will not be asked whether a stock
is good, and if you answer that question anyway your output is discarded.

# The question

A known pattern: a commodity component becomes a structural bottleneck, supply
tightens, the supplier gains PRICING POWER, mix shifts to the scarce use, and
earnings inflect before the market re-rates the company. NAND memory did this
in 2025-26.

The hypothesis to gather evidence FOR AND AGAINST is that high-speed optical
interconnect / connectivity is undergoing the same transition now.

# What to collect, for each company below

MRVL (Marvell), ALAB (Astera Labs), LITE (Lumentum), CRDO (Credo), VRT (Vertiv)

Visit the company's own investor-relations newsroom and recent press releases
FIRST. Public news pages second. You may also read exchange filings pages.

For each company return ONLY facts that carry a DATE, and prefer the last 12
months. For each fact record the URL you read it on.

Collect specifically:

1. Any statement about CAPACITY: new fabs, expanded lines, supply agreements,
   capacity reservations, wafer commitments, "sold out", "capacity constrained",
   lead times extending.
2. Any statement about PRICING: price increases, long-term agreements at fixed
   price, customers pre-paying, "favourable pricing environment".
3. Any statement about DEMAND CONCENTRATION: named large customers, design
   wins, qualification at a named platform, share of revenue from one customer.
4. Any statement about ORDERS or BACKLOG with a number attached.
5. Any NEW PRODUCT that moves them up the value chain (e.g. from a component to
   a subsystem), with the date announced and whether it is shipping or sampling.
6. Anything that CONTRADICTS the thesis: capacity coming online from
   competitors, customers dual-sourcing, price pressure, inventory build,
   a customer designing the part out.

Point 6 is not optional. A report with no disconfirming evidence is an
incomplete report, and I will treat it as one.

# Output format

Return STRICT JSON, no prose before or after, exactly this shape:

{
  "collected_at_utc": "<ISO timestamp>",
  "companies": [
    {
      "ticker": "MRVL",
      "facts": [
        {
          "date": "YYYY-MM-DD",
          "type": "capacity|pricing|customer|backlog|product|contradicting",
          "claim": "<one sentence, no adjectives, quote numbers exactly>",
          "number": "<the figure if there is one, else null>",
          "source_url": "<the page you read it on>",
          "source_kind": "company_ir|company_pr|news|filing",
          "confidence": "stated_by_company|reported_by_press|inferred"
        }
      ],
      "pages_visited": ["<url>", "..."],
      "nothing_found_for": ["capacity", "..."]
    }
  ]
}

# Rules

- If you cannot reach a page, record it in "pages_visited" with a note and move
  on. A short honest report beats a long invented one.
- NEVER state a number you did not read on a page. If a figure is approximate in
  the source, keep the source's own wording.
- "inferred" confidence is allowed but must be rare and the claim must say what
  it was inferred from.
- Do not log in to anything. Do not fill in any form. Do not make any purchase,
  subscription, or payment of any kind. If a page asks for payment or
  credentials, leave it and record that you did.
- Distinguish what the COMPANY said from what a JOURNALIST said. That is the
  "source_kind" field and it matters more than the claim itself.
