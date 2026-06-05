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

// Hop-by-hop / framing headers the runtime must recompute. Forwarding stale
// values from the upstream corrupts the response body.
const STRIP_RESPONSE_HEADERS = new Set([
    "content-encoding",
    "content-length",
    "transfer-encoding",
    "connection",
]);

async function proxyToBackend(request: NextRequest): Promise<Response> {
    const url = request.nextUrl;
    // Django uses APPEND_SLASH, so ensure exactly one trailing slash on the path
    // (the query string is preserved separately).
    const path = url.pathname.endsWith("/") ? url.pathname : `${url.pathname}/`;
    const target = `${API_BASE}${path}${url.search}`;

    const headers = new Headers(request.headers);
    headers.delete("host"); // let fetch set Host to the backend origin
    headers.set("x-forwarded-host", FRONTEND_HOST);
    headers.set("x-forwarded-proto", FRONTEND_PROTO);

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
        return new Response("Bad Gateway", { status: 502 });
    }

    // Rebuild headers: drop framing headers, and re-append each Set-Cookie
    // individually (a plain copy folds multiple Set-Cookie into one).
    const outHeaders = new Headers();
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

    // Transparent reverse proxy to Django for the browser-facing prefixes.
    if (PROXY_PREFIXES.some((p) => pathname.startsWith(p))) {
        return proxyToBackend(request);
    }

    // --- Proactive access-token refresh for page (document) requests ---
    // Access token still present (or user has neither) - nothing to do.
    if (request.cookies.has(ACCESS_COOKIE)) {
        return NextResponse.next();
    }
    const refresh = request.cookies.get(REFRESH_COOKIE);
    if (!refresh) {
        return NextResponse.next();
    }

    const csrf = request.cookies.get(CSRF_COOKIE);
    const upstreamCookies = [`${REFRESH_COOKIE}=${refresh.value}`];
    if (csrf) upstreamCookies.push(`${CSRF_COOKIE}=${csrf.value}`);

    // TODO: race condition - if multiple tabs hit this at the same moment the access cookie expires, the first refresh
    // consumes the refresh token (BLACKLIST_AFTER_ROTATION) and the rest get 401 here, rendering logged-out until re-login.
    // Fix later via single-flight refresh (shared cache lock by refresh-token JTI) or a brief blacklist grace window on the backend.
    const refreshResp = await fetch(`${API_BASE}/auth/token/refresh/`, {
        method: "POST",
        headers: {
            cookie: upstreamCookies.join("; "),
            ...(csrf ? { "X-CSRFToken": csrf.value } : {}),
            // CSRF middleware accepts requests whose Origin matches CSRF_TRUSTED_ORIGINS.
            origin: FRONTEND_URL,
        },
    });

    if (!refreshResp.ok) {
        // Refresh failed (expired/blacklisted). Wipe the stale refresh cookie and let the downstream render in logged-out state; user re-logs in.
        const response = NextResponse.next();
        response.cookies.delete(REFRESH_COOKIE);
        return response;
    }

    const setCookieHeaders = refreshResp.headers.getSetCookie();
    const overrides = new Map<string, string>();
    for (const sc of setCookieHeaders) {
        const parsed = extractCookieNameValue(sc);
        if (parsed) overrides.set(parsed.name, parsed.value);
    }

    // Override the Cookie header for downstream rendering so getCurrentUser() sees the freshly minted access token within the same request cycle.
    const newCookieHeader = rebuildCookieHeader(request.headers.get("cookie") ?? "", overrides);
    const requestHeaders = new Headers(request.headers);
    requestHeaders.set("cookie", newCookieHeader);

    const response = NextResponse.next({ request: { headers: requestHeaders } });

    // Forward Set-Cookie from Django to the browser so subsequent requests carry the rotated tokens.
    for (const sc of setCookieHeaders) {
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
