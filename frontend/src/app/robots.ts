import type { MetadataRoute } from "next";

// Static by construction (no request-time input), and declared as such so the
// desktop `output: "export"` build can emit it as a plain file. Harmless for the
// standalone build, where it was already computed once per deploy.
export const dynamic = "force-static";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/api/"],
      },
    ],
    sitemap: "https://aegis-finance-six.vercel.app/sitemap.xml",
  };
}
