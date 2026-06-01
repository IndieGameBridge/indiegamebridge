// SSR-side fetch wrapper with a single retry on connection errors.
//
// The Django dev server (`runserver`) doesn't hold HTTP/1.1 keep-alive sockets
// the way Node's undici expects: sockets get closed quickly and undici tries
// to reuse them anyway, surfacing as `TypeError: fetch failed` /
// `ECONNRESET`. A retry opens a fresh socket. Brief outages during runserver
// autoreload (`ECONNREFUSED`) are also covered. A genuinely down backend
// still fails on the retry, so this doesn't paper over real issues.
export async function serverFetch(url: string, init?: RequestInit): Promise<Response> {
    try {
        return await fetch(url, init);
    } catch {
        return await fetch(url, init);
    }
}
