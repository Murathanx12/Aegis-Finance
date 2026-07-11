import { NextRequest, NextResponse } from "next/server";

/**
 * Private-area gate for /dev (the operator dashboard).
 *
 * How it works: set DEV_ACCESS_KEY in the Vercel project env. Visit
 * /dev?key=<that value> once per browser — the key is stored as an
 * httpOnly cookie and checked here on every /dev request. Wrong/missing
 * key → redirect home. If DEV_ACCESS_KEY is unset (local dev), /dev is open.
 *
 * This is personal-use protection (keeps the operator view and its
 * warnings/registry off the public site), not bank-grade auth. The RAW
 * Optimus brain (identity/private projects) must never be served from this
 * origin regardless — only the sanitized public showcase is deployed.
 */
export function middleware(request: NextRequest) {
  const accessKey = process.env.DEV_ACCESS_KEY;
  if (!accessKey) return NextResponse.next(); // local dev: open

  const url = request.nextUrl;
  const queryKey = url.searchParams.get("key");
  if (queryKey === accessKey) {
    // Set the cookie and strip the key from the URL
    const clean = url.clone();
    clean.searchParams.delete("key");
    const res = NextResponse.redirect(clean);
    res.cookies.set("aegis_dev_key", accessKey, {
      httpOnly: true,
      secure: true,
      sameSite: "lax",
      maxAge: 60 * 60 * 24 * 90, // 90 days
      path: "/",
    });
    return res;
  }

  const cookieKey = request.cookies.get("aegis_dev_key")?.value;
  if (cookieKey === accessKey) return NextResponse.next();

  return NextResponse.redirect(new URL("/", request.url));
}

export const config = {
  matcher: ["/dev/:path*", "/dev"],
};
