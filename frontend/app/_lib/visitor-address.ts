// The headers that carry the visitor's address on a request this server makes to
// the API on their behalf: the backend's per-IP rate limits count by it, and
// sign-in records keep it.
//
// For a Worker's request to a host in its own zone, as the API is, Cloudflare
// takes the client address from X-Real-IP. That header is filled from
// CF-Connecting-IP, the address Cloudflare itself saw: X-Real-IP may arrive from
// the visitor, so a script could make up a new address for every request and
// never reach a limit. Off Cloudflare, as in local dev, CF-Connecting-IP isn't
// there and X-Real-IP passes on as it came; X-Forwarded-For serves a backend
// reached directly.
export function visitorAddressHeaders(incoming: { get(name: string): string | null }): Record<string, string> {
    const address = incoming.get("cf-connecting-ip") ?? incoming.get("x-real-ip");
    const forwardedFor = incoming.get("x-forwarded-for");
    return {
        ...(address ? { "x-real-ip": address } : {}),
        ...(forwardedFor ? { "x-forwarded-for": forwardedFor } : {}),
    };
}
