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
// It also passes the visitor's address on, in the headers middleware.ts passes
// on for the browser's own calls, since the backend's per-IP rate limit counts
// by it. For a Worker's request to a host in its own zone, as the API is,
// Cloudflare takes the client address from X-Real-IP; X-Forwarded-For serves
// a backend reached directly, as in local dev. Without them, every page built
// for a logged-out visitor counts as the Worker's own address
// (2a06:98c0:3600::103), so they all share a single allowance. A route built
// ahead of any request, like the sitemap, has no visitor and passes
// { visitor: false }.
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
    const incoming = await headers();
    const realIp = incoming.get("x-real-ip") ?? incoming.get("cf-connecting-ip");
    const forwardedFor = incoming.get("x-forwarded-for");
    if (!realIp && !forwardedFor) return init;
    const merged = new Headers(init?.headers);
    if (realIp) merged.set("x-real-ip", realIp);
    if (forwardedFor) merged.set("x-forwarded-for", forwardedFor);
    return { ...init, headers: merged };
}
