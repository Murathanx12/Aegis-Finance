import { POPULAR_TICKERS } from "@/lib/tickers";

/**
 * Present only so the static desktop export knows which detail routes to emit.
 * The standalone build renders this segment on demand exactly as before; this
 * merely pre-renders the shortcut tickers there too.
 */
export function generateStaticParams() {
  return POPULAR_TICKERS.map((ticker) => ({ ticker }));
}

export default function StockTickerLayout({ children }: { children: React.ReactNode }) {
  return children;
}
