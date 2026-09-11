import { POPULAR_TICKERS, DESKTOP_TICKER_SHELL } from "@/lib/tickers";

/**
 * Present only so the static desktop export knows which detail routes to emit.
 * The standalone build renders this segment on demand exactly as before; this
 * merely pre-renders the shortcut tickers there too.
 *
 * The desktop build emits ONE extra path, `DESKTOP_TICKER_SHELL`. FastAPI serves
 * that page for any symbol without a folder of its own, and the page reads the
 * symbol from the URL -- which is why the packaged app no longer 404s on
 * everything outside the twelve shortcuts. It is added only under
 * `AEGIS_DESKTOP_BUILD=1`: on the standalone deploy the segment is dynamic and a
 * literal `/stock/__ticker__` route would be a dead page nobody asked for.
 */
export function generateStaticParams() {
  const tickers: string[] = [...POPULAR_TICKERS];
  if (process.env.AEGIS_DESKTOP_BUILD === "1") tickers.push(DESKTOP_TICKER_SHELL);
  return tickers.map((ticker) => ({ ticker }));
}

export default function StockTickerLayout({ children }: { children: React.ReactNode }) {
  return children;
}
