import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The backend prefixes (/accounts, /auth, /api) are reverse-proxied to Django
  // in middleware.ts, not via rewrites — the OAuth flow needs a transparent
  // proxy (forwarded host + pass-through redirects) that rewrites can't provide.
  //
  // Django uses APPEND_SLASH and the proxy forwards the browser's path verbatim,
  // so suppress Next's own trailing-slash redirects to avoid loops/flicker.
  skipTrailingSlashRedirect: true,
};

export default nextConfig;
