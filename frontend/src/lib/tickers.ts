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

/**
 * The one extra route the DESKTOP export pre-renders: a blank `[ticker]` shell
 * that reads its symbol from the browser's URL instead of from the build.
 *
 * `output: "export"` can only emit the paths named above, so a packaged app
 * 404'd on every other symbol -- and the universe is ~3,000 names. The detail
 * page fetches everything from `/api/stock/{ticker}` at runtime, so one shell
 * serves them all, including symbols that did not exist at build time.
 * `mount_desktop_frontend` (backend/main.py) hands `/stock/<ANY>` to this page.
 */
export const DESKTOP_TICKER_SHELL = "__ticker__";
