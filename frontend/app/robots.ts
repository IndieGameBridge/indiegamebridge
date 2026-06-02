import type { MetadataRoute } from "next";

// Server-side route handler, so the non-public FRONTEND_URL env is available.
const baseUrl = process.env.FRONTEND_URL ?? "http://localhost:3000";

export default function robots(): MetadataRoute.Robots {
    return {
        rules: {
            userAgent: "*",
            allow: "/",
            // Everything we keep out of the index: the secondary pages we don't
            // want crawled, the auth-gated app pages, and the Django proxy
            // prefixes from next.config.ts. Home and /privacy stay crawlable.
            disallow: [
                "/login",
                "/optout",
                "/contact",
                "/account",
                "/streamers",
                "/accounts/",
                "/auth/",
                "/api/",
            ],
        },
        sitemap: `${baseUrl}/sitemap.xml`,
        host: baseUrl,
    };
}
