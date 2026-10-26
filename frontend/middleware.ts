import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// NOTE: This is the `middleware` convention, not Next 16's `proxy`. Next 16's
// proxy.ts runs on the Node.js runtime (and can't be configured to edge), but
// the OpenNext Cloudflare adapter only supports *edge* middleware. The
// middleware convention still gives us the edge runtime, so we keep it here.

const ACCESS_COOKIE = "ig_access";
const REFRESH_COOKIE = "ig_refresh";
const CSRF_COOKIE = "csrftoken";

const API_BASE = process.env.API_BASE_URL ?? "http://localhost:8000";
const FRONTEND_URL = process.env.FRONTEND_URL ?? "http://localhost:3000";
const FRONTEND_HOST = new URL(FRONTEND_URL).host;
const FRONTEND_PROTO = new URL(FRONTEND_URL).protocol.replace(":", "");

// Django URL prefixes the browser must reach directly. We proxy them here
// instead of via next.config rewrites because the OAuth dance needs a TRANSPARENT
// reverse proxy: forward X-Forwarded-Host so allauth builds redirect_uri against
// the frontend origin, and pass 3xx redirects + Set-Cookie straight through to
// the browser. Next/OpenNext rewrites follow redirects server-side and don't
// forward the host, which breaks the Twitch login flow.
const PROXY_PREFIXES = ["/accounts/", "/auth/", "/api/"];

// Proxied calls that never act as the logged-in user, so an expired access
// token isn't refreshed for them: the OAuth dance (it runs on allauth's
// session), logout, and the refresh endpoint itself.
const NO_REFRESH_PREFIXES = ["/accounts/", "/auth/logout/", "/auth/token/refresh/"];

// Hop-by-hop / framing headers the runtime must recompute. Forwarding stale
// values from the upstream corrupts the response body.
const STRIP_RESPONSE_HEADERS = new Set([
    "content-encoding",
    "content-length",
    "transfer-encoding",
    "connection",
]);

type Refresh = {
    // The request's Cookie header with the new tokens in, for whatever handles
    // the request next. Absent when the refresh token was turned down.
    cookieHeader?: string;
    // Set-Cookie headers to pass on to the browser.
    setCookies: string[];
};

async function proxyToBackend(request: NextRequest, refresh: Refresh | null): Promise<Response> {
    const url = request.nextUrl;
    // Django uses APPEND_SLASH, so ensure exactly one trailing slash on the path
    // (the query string is preserved separately).
    const path = url.pathname.endsWith("/") ? url.pathname : `${url.pathname}/`;
    const target = `${API_BASE}${path}${url.search}`;

    const headers = new Headers(request.headers);
    headers.delete("host"); // let fetch set Host to the backend origin
    headers.set("x-forwarded-host", FRONTEND_HOST);
    headers.set("x-forwarded-proto", FRONTEND_PROTO);
    if (refresh?.cookieHeader) headers.set("cookie", refresh.cookieHeader);

    // The refresh's cookies go first, so a response that sets or clears the same
    // ones (opt-out, account deletion) has the last word. They go out even if
    // Django can't be reached: the old refresh token is spent either way.
    const outHeaders = new Headers();
    for (const cookie of refresh?.setCookies ?? []) {
        outHeaders.append("set-cookie", cookie);
    }

    const hasBody = request.method !== "GET" && request.method !== "HEAD";
    let upstream: Response;
    try {
        upstream = await fetch(target, {
            method: request.method,
            headers,
            body: hasBody ? request.body : undefined,
            redirect: "manual", // pass the backend's 3xx through to the browser
            // Required when streaming a request body on the edge runtime.
            ...(hasBody ? { duplex: "half" } : {}),
        } as RequestInit);
    } catch {
        return new Response("Bad Gateway", { status: 502, headers: outHeaders });
    }

    // Rebuild headers: drop framing headers, and re-append each Set-Cookie
    // individually (a plain copy folds multiple Set-Cookie into one).
    upstream.headers.forEach((value, key) => {
        const lower = key.toLowerCase();
        if (lower === "set-cookie" || STRIP_RESPONSE_HEADERS.has(lower)) return;
        outHeaders.set(key, value);
    });
    for (const cookie of upstream.headers.getSetCookie()) {
        outHeaders.append("set-cookie", cookie);
    }

    // Django emits relative redirect targets (e.g. "/auth/finalize-login/..").
    // Absolutize them against the request origin: OpenNext's routing layer runs
    // `new URL(location)` on the response and throws "Invalid URL string" on a
    // bare path. (Absolute upstream Locations pass through unchanged.)
    const location = outHeaders.get("location");
    if (location) {
        outHeaders.set("location", new URL(location, request.url).toString());
    }

    return new Response(upstream.body, {
        status: upstream.status,
        statusText: upstream.statusText,
        headers: outHeaders,
    });
}

// Trades the refresh token for a new access token (and a rotated refresh
// token). Concurrent refreshes with the same token are safe: the backend gives
// them all the same new pair for a short while. Returns null when the backend
// couldn't answer - down or throttling - so the cookie stays for the next
// request to try again.
async function refreshTokens(request: NextRequest, refreshToken: string): Promise<Refresh | null> {
    const csrf = request.cookies.get(CSRF_COOKIE);
    const upstreamCookies = [`${REFRESH_COOKIE}=${refreshToken}`];
    if (csrf) upstreamCookies.push(`${CSRF_COOKIE}=${csrf.value}`);
    // Lets the backend's per-IP throttle count the visitor, as on proxied calls.
    const forwardedFor = request.headers.get("x-forwarded-for");

    let refreshResp: Response;
    try {
        refreshResp = await fetch(`${API_BASE}/auth/token/refresh/`, {
            method: "POST",
            headers: {
                cookie: upstreamCookies.join("; "),
                ...(csrf ? { "X-CSRFToken": csrf.value } : {}),
                ...(forwardedFor ? { "x-forwarded-for": forwardedFor } : {}),
                // CSRF middleware accepts requests whose Origin matches CSRF_TRUSTED_ORIGINS.
                origin: FRONTEND_URL,
            },
        });
    } catch {
        return null;
    }
    if (refreshResp.status === 429 || refreshResp.status >= 500) {
        return null;
    }
    if (!refreshResp.ok) {
        // Turned down (expired, blacklisted, CSRF). Wipe the stale refresh cookie;
        // the request goes on logged out and the user logs in again.
        return { setCookies: [`${REFRESH_COOKIE}=; Path=/; Max-Age=0`] };
    }

    const setCookies = refreshResp.headers.getSetCookie();
    const overrides = new Map<string, string>();
    for (const sc of setCookies) {
        const parsed = extractCookieNameValue(sc);
        if (parsed) overrides.set(parsed.name, parsed.value);
    }
    return {
        cookieHeader: rebuildCookieHeader(request.headers.get("cookie") ?? "", overrides),
        setCookies,
    };
}

function extractCookieNameValue(setCookie: string): { name: string; value: string } | null {
    const firstSegment = setCookie.split(";")[0];
    const eq = firstSegment.indexOf("=");
    if (eq <= 0) return null;
    return { name: firstSegment.slice(0, eq).trim(), value: firstSegment.slice(eq + 1).trim() };
}

function rebuildCookieHeader(original: string, overrides: Map<string, string>): string {
    const parts = original ? original.split(";").map((p) => p.trim()).filter(Boolean) : [];
    const seen = new Set<string>();
    const merged: string[] = [];
    for (const part of parts) {
        const eq = part.indexOf("=");
        if (eq <= 0) continue;
        const name = part.slice(0, eq);
        seen.add(name);
        if (overrides.has(name)) {
            merged.push(`${name}=${overrides.get(name)}`);
        } else {
            merged.push(part);
        }
    }
    for (const [name, value] of overrides) {
        if (!seen.has(name)) merged.push(`${name}=${value}`);
    }
    return merged.join("; ");
}

export async function middleware(request: NextRequest) {
    const { pathname } = request.nextUrl;

    // The access cookie runs out with its token; the refresh cookie lasts two
    // weeks. When only the latter is left, trade it in before anything below -
    // a proxied API call or a page render - needs the user.
    const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value;
    const refresh =
        refreshToken &&
        !request.cookies.has(ACCESS_COOKIE) &&
        !NO_REFRESH_PREFIXES.some((p) => pathname.startsWith(p))
            ? await refreshTokens(request, refreshToken)
            : null;

    // Transparent reverse proxy to Django for the browser-facing prefixes.
    if (PROXY_PREFIXES.some((p) => pathname.startsWith(p))) {
        return proxyToBackend(request, refresh);
    }

    if (!refresh) {
        return NextResponse.next();
    }

    // Override the Cookie header for downstream rendering so getCurrentUser() sees the freshly minted access token within the same request cycle.
    const requestHeaders = new Headers(request.headers);
    if (refresh.cookieHeader) requestHeaders.set("cookie", refresh.cookieHeader);
    const response = NextResponse.next({ request: { headers: requestHeaders } });

    // Forward Set-Cookie from Django to the browser so subsequent requests carry the rotated tokens.
    for (const sc of refresh.setCookies) {
        response.headers.append("set-cookie", sc);
    }
    return response;
}

export const config = {
    matcher: [
        // Run on every page/api request except Next internals and static files.
        "/((?!_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml).*)",
    ],
};
