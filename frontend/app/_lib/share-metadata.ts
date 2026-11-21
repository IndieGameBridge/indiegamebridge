import type { Metadata } from "next";

// The picture a shared link shows, in public/. Relative, so Next resolves it against
// metadataBase like the pages' own URLs.
const SHARE_IMAGE = {
    url: "/og-image.png",
    width: 1200,
    height: 630,
    alt: "IndieGameBridge: find Twitch streamers for your indie game",
};

// What every page's Open Graph and X card share. Next merges metadata shallowly, so a page
// that sets openGraph or twitter replaces the layout's whole object, picture included: such
// a page spreads these in and adds its own title, description and url.
export const SHARED_OPEN_GRAPH = {
    siteName: "IndieGameBridge",
    type: "website",
    locale: "en_US",
    images: [SHARE_IMAGE],
} satisfies NonNullable<Metadata["openGraph"]>;

export const SHARED_TWITTER = {
    card: "summary_large_image",
    images: [SHARE_IMAGE],
} satisfies NonNullable<Metadata["twitter"]>;
