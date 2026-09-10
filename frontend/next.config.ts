import type { NextConfig } from "next";

/**
 * Two build modes from one tree.
 *
 * - default (`AEGIS_DESKTOP_BUILD` unset): `output: "standalone"` — the Railway /
 *   Vercel deploy, which has a Node runtime and the image optimizer.
 * - `AEGIS_DESKTOP_BUILD=1`: `output: "export"` — a pure static bundle in `out/`,
 *   which FastAPI serves with `StaticFiles(html=True)` so the packaged desktop app
 *   ships Python only (no Node runtime inside the .exe).
 *
 * The export mode also turns the image optimizer off (it needs a server) and turns
 * trailing slashes on, so every route lands as `out/<route>/index.html` and a plain
 * static file server resolves it as a directory index.
 */
const DESKTOP_BUILD = process.env.AEGIS_DESKTOP_BUILD === "1";

const nextConfig: NextConfig = DESKTOP_BUILD
  ? {
      output: "export",
      images: { unoptimized: true },
      trailingSlash: true,
      // Reaches the browser bundle: the desktop pages must call the SAME origin
      // that served them (the shell picks a free port), not an absolute :8000.
      env: { NEXT_PUBLIC_AEGIS_DESKTOP_BUILD: "1" },
    }
  : {
      output: "standalone",
    };

export default nextConfig;
