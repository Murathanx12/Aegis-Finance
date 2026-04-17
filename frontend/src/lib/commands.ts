/**
 * Bloomberg-style command grammar for the Cmd/Ctrl-K palette.
 *
 * Users type `AAPL GP`, `SPY PORT`, `ECO`, `WEI`, `NI AAPL`, etc.
 * parseCommand() maps typed text → navigation action. The command registry
 * is also surfaced in the palette itself as a discoverable list.
 *
 * Intentionally dependency-free so it can be unit-tested and reused outside
 * React components.
 */

export type CommandKind = "function" | "ticker" | "ticker+function";

export type CommandAction = {
  href: string;
  label: string;
  functionCode?: string;
  ticker?: string;
};

export type CommandDef = {
  code: string;
  label: string;
  description: string;
  href: string | ((ticker?: string) => string);
  /** Whether the function expects a ticker. */
  needsTicker?: boolean;
  /** Alternate codes that should also match this function. */
  aliases?: string[];
  /** Keywords for search ranking when user types natural language. */
  keywords?: string[];
};

/**
 * Canonical function registry. Codes are uppercase 2-6 letter mnemonics
 * modeled on Bloomberg Terminal conventions. Keep short — muscle memory.
 */
export const COMMANDS: CommandDef[] = [
  // Market-wide
  {
    code: "DASH",
    label: "Dashboard",
    description: "Market overview — regime, risk, sector heat, intermarkets",
    href: "/",
    aliases: ["HOME", "OVERVIEW"],
    keywords: ["market", "overview", "dashboard"],
  },
  {
    code: "PORT",
    label: "Portfolio",
    description: "Your holdings — risk, factors, attribution, stress",
    href: "/portfolio",
    aliases: ["PORTFOLIO", "P"],
    keywords: ["holdings", "allocation", "risk", "tearsheet"],
  },
  {
    code: "EQS",
    label: "Stock Screener",
    description: "Rank tickers by Sharpe, signal, factor grades",
    href: "/screener",
    aliases: ["SCREENER", "SCREEN"],
    keywords: ["screener", "rank", "sort", "filter"],
  },
  {
    code: "GP",
    label: "Stock Detail",
    description: "Per-ticker analysis — prices, fundamentals, SHAP",
    href: (t) => (t ? `/stock/${encodeURIComponent(t)}` : "/stock"),
    needsTicker: true,
    aliases: ["STOCK", "GIP", "DES", "EQRP"],
    keywords: ["ticker", "price", "chart", "fundamentals"],
  },
  {
    code: "NI",
    label: "News & Intel",
    description: "Headlines, sentiment, event risk; optional per-ticker",
    href: (t) => (t ? `/news?ticker=${encodeURIComponent(t)}` : "/news"),
    aliases: ["NEWS", "TOP"],
    keywords: ["news", "headlines", "sentiment", "gdelt"],
  },
  {
    code: "ECO",
    label: "Market Outlook",
    description: "Macro indicators, regime, recession odds, outlook",
    href: "/outlook",
    aliases: ["MACRO", "OUTLOOK"],
    keywords: ["economy", "macro", "fed", "recession"],
  },
  {
    code: "WEI",
    label: "World Markets",
    description: "Global indices, FX, commodities, yields heat grid",
    href: "/world",
    aliases: ["WORLD", "GLOBAL"],
    keywords: ["global", "indices", "fx", "commodities"],
  },
  {
    code: "SECT",
    label: "Sectors",
    description: "S&P sector ranking and rotation model",
    href: "/sectors",
    aliases: ["SECTORS", "SECTOR"],
    keywords: ["sector", "rotation"],
  },
  {
    code: "MC",
    label: "Simulation",
    description: "S&P 500 Monte Carlo projection",
    href: "/simulation",
    aliases: ["SIM", "SIMULATION", "MONTE"],
    keywords: ["monte carlo", "simulation", "projection"],
  },
  {
    code: "CRASH",
    label: "Crash Risk",
    description: "3/6/12-month crash probability with SHAP explanation",
    href: "/crash",
    aliases: ["RISK", "TAIL"],
    keywords: ["crash", "downside", "drawdown", "tail"],
  },
  {
    code: "RETIRE",
    label: "Retirement",
    description: "Compound growth + safe withdrawal + Monte Carlo",
    href: "/retirement",
    aliases: ["RET", "SAVINGS"],
    keywords: ["retirement", "savings", "compound"],
  },
  {
    code: "COPILOT",
    label: "Copilot",
    description: "Natural-language chat over the engine's analytics",
    href: "/copilot",
    aliases: ["AI", "CHAT", "ASK"],
    keywords: ["ai", "chat", "copilot", "assistant"],
  },
  {
    code: "ABOUT",
    label: "About",
    description: "Methodology and disclaimers",
    href: "/about",
    aliases: ["INFO", "DOCS"],
    keywords: ["about", "methodology"],
  },
  {
    code: "WORK",
    label: "Workspace",
    description: "Saved 2×2 / 3×2 tile layout of your favourite views",
    href: "/workspace",
    aliases: ["WKS", "TILES", "LAYOUT"],
    keywords: ["workspace", "tiles", "layout"],
  },
  {
    code: "WATCH",
    label: "Watchlist",
    description: "Your personal watchlist — tickers with live quotes",
    href: "/watchlist",
    aliases: ["WL", "LIST", "FAVES"],
    keywords: ["watchlist", "favorites", "tracking"],
  },
  {
    code: "HELP",
    label: "Keyboard Shortcuts",
    description: "Show the keyboard shortcut cheatsheet",
    href: "/?shortcuts=1",
    aliases: ["?", "KEYS", "SHORTCUTS"],
    keywords: ["shortcuts", "keys", "help"],
  },
];

/** Fast lookup by code or alias, uppercased. */
const BY_CODE: Record<string, CommandDef> = (() => {
  const map: Record<string, CommandDef> = {};
  for (const c of COMMANDS) {
    map[c.code] = c;
    for (const a of c.aliases ?? []) map[a] = c;
  }
  return map;
})();

/** A-Z uppercased, 1-6 chars, may contain . or - (e.g. BRK.B, RDS-A). */
const TICKER_RE = /^[A-Z][A-Z0-9.\-^]{0,9}$/;
const FUNCTION_RE = /^[A-Z?][A-Z0-9]{0,8}$/;

export function isTickerLike(tok: string): boolean {
  if (!TICKER_RE.test(tok)) return false;
  // Don't misread function codes as tickers
  return !(tok in BY_CODE);
}

export function isFunction(tok: string): boolean {
  return FUNCTION_RE.test(tok) && tok in BY_CODE;
}

/**
 * Parse a command string into an action.
 *
 * Examples:
 *   "AAPL"         → /stock/AAPL (default GP)
 *   "AAPL PORT"    → /portfolio (PORT ignores ticker — warn via label)
 *   "AAPL GP"      → /stock/AAPL
 *   "GP AAPL"      → /stock/AAPL
 *   "PORT"         → /portfolio
 *   "ECO"          → /outlook
 *   "NI AAPL"      → /news?ticker=AAPL
 *   "? "           → shortcut cheatsheet
 *   ""             → null
 */
export function parseCommand(raw: string): CommandAction | null {
  const text = raw.trim().toUpperCase();
  if (!text) return null;

  const tokens = text.split(/\s+/);
  // Single token: function OR ticker
  if (tokens.length === 1) {
    const tok = tokens[0];
    if (tok in BY_CODE) {
      const def = BY_CODE[tok];
      if (def.needsTicker) return null; // needs a ticker — incomplete
      return {
        href: typeof def.href === "function" ? def.href() : def.href,
        label: def.label,
        functionCode: def.code,
      };
    }
    if (isTickerLike(tok)) {
      return {
        href: `/stock/${encodeURIComponent(tok)}`,
        label: `Stock: ${tok}`,
        ticker: tok,
        functionCode: "GP",
      };
    }
    return null;
  }

  // Two tokens: ticker + function, in either order
  if (tokens.length === 2) {
    const [a, b] = tokens;
    // Function + ticker
    if (a in BY_CODE && isTickerLike(b)) {
      const def = BY_CODE[a];
      const href = typeof def.href === "function" ? def.href(b) : def.href;
      return {
        href,
        label: `${def.label} — ${b}`,
        functionCode: def.code,
        ticker: b,
      };
    }
    // Ticker + function
    if (isTickerLike(a) && b in BY_CODE) {
      const def = BY_CODE[b];
      const href = typeof def.href === "function" ? def.href(a) : def.href;
      return {
        href,
        label: `${def.label} — ${a}`,
        functionCode: def.code,
        ticker: a,
      };
    }
  }

  return null;
}

/** Fuzzy search over function codes + labels + keywords. */
export function searchCommands(query: string, limit = 8): CommandDef[] {
  const q = query.trim().toUpperCase();
  if (!q) return COMMANDS.slice(0, limit);
  const scored: Array<{ def: CommandDef; score: number }> = [];
  for (const def of COMMANDS) {
    let score = 0;
    if (def.code === q) score += 100;
    if (def.code.startsWith(q)) score += 50;
    if ((def.aliases ?? []).some((a) => a === q)) score += 80;
    if ((def.aliases ?? []).some((a) => a.startsWith(q))) score += 30;
    if (def.label.toUpperCase().includes(q)) score += 15;
    for (const kw of def.keywords ?? []) {
      if (kw.toUpperCase().includes(q)) score += 5;
    }
    if (score > 0) scored.push({ def, score });
  }
  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, limit).map((s) => s.def);
}

/** Public helper so UI can render the mnemonic list. */
export function allCommands(): CommandDef[] {
  return COMMANDS;
}
