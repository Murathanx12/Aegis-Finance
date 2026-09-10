/**
 * The ticker shortcuts the search page offers, in one place because the static
 * desktop build also needs them: `output: "export"` has no server, so a dynamic
 * segment must name the paths it emits up front (`generateStaticParams`).
 *
 * This is a list of ROUTE names, not data — no number on any page comes from it.
 * On the normal (standalone) build the segment stays dynamic and any ticker works;
 * in the exported desktop bundle only these detail pages exist, and the desktop
 * app's own surface is `/desktop/*`, which talks to FastAPI directly.
 */
export const POPULAR_TICKERS = [
  "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META",
  "TSLA", "JPM", "JNJ", "V", "UNH", "XOM",
] as const;
