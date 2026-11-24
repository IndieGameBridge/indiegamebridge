import { defineCloudflareConfig } from "@opennextjs/cloudflare";

// Default configuration: packages the Next.js server (server components +
// middleware.ts) into a single Cloudflare Worker. No incremental (ISR) cache
// backend is wired yet, so the two routes with `revalidate`, /sitemap.xml and
// /llms.txt, are built afresh on every request: the sitemap, with every game
// page in it, takes about 2 seconds and 6 API calls. Add an R2 or KV cache
// here if that ever matters.
export default defineCloudflareConfig();
