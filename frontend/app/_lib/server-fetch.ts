import { headers } from "next/headers";

// SSR-side fetch wrapper with a single retry on connection errors.
//
// The Django dev server (`runserver`) doesn't hold HTTP/1.1 keep-alive sockets
// the way Node's undici expects: sockets get closed quickly and undici tries
// to reuse them anyway, surfacing as `TypeError: fetch failed` /
// `ECONNRESET`. A retry opens a fresh socket. Brief outages during runserver
// autoreload (`ECONNREFUSED`) are also covered. A genuinely down backend
// still fails on the retry, so this doesn't paper over real issues.
//
// It also passes the visitor's address on, as middleware.ts does for the
// browser's own calls, since the backend's per-IP rate limit counts by it.
// Without it, every page built for a logged-out visitor counts as the
// Cloudflare Worker's one address (2a06:98c0:3600::103), so they all share a
// single allowance. A route built ahead of any request, like the sitemap,
// has no visitor and passes { visitor: false }.
export async function serverFetch(
    url: string,
    init?: RequestInit,
    { visitor = true }: { visitor?: boolean } = {},
): Promise<Response> {
    const request = visitor ? await withVisitorAddress(init) : init;
    try {
        return await fetch(url, request);
    } catch {
        return await fetch(url, request);
    }
}

async function withVisitorAddress(init?: RequestInit): Promise<RequestInit | undefined> {
    const forwardedFor = (await headers()).get("x-forwarded-for");
    if (!forwardedFor) return init;
    const merged = new Headers(init?.headers);
    merged.set("x-forwarded-for", forwardedFor);
    return { ...init, headers: merged };
}
