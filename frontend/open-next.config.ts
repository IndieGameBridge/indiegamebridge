import { defineCloudflareConfig } from "@opennextjs/cloudflare";

// Default configuration: packages the Next.js server (server components +
// proxy.ts middleware) into a single Cloudflare Worker. No incremental/ISR
// cache backend is wired yet — the only revalidated route is /sitemap.xml,
// which is cheap to regenerate. Add an R2/KV cache here later if needed.
export default defineCloudflareConfig();
