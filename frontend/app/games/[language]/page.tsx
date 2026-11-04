import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { getCurrentUser } from "../../_lib/auth";
import {
    GamesContent,
    GamesSearchParams,
    GamesView,
    fetchGamesContent,
    gamesMetadata,
} from "../_components/GamesView";

// Reads auth cookies (for the header) + live backend data per request, so never
// prerender at build time. Render on demand on the Worker.
export const dynamic = "force-dynamic";

type Props = {
    params: Promise<{ language: string }>;
    searchParams: Promise<GamesSearchParams>;
};

// The language's page by its slug, e.g. "japanese"; any other slug is a 404.
function languagePage(content: GamesContent, slug: string) {
    const page = content.language_pages.find((one) => one.slug === slug);
    if (!page) {
        notFound();
    }
    return page;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
    const { language } = await params;
    const content = await fetchGamesContent();
    return gamesMetadata(content, languagePage(content, language));
}

export default async function GamesLanguagePage({ params, searchParams }: Props) {
    const [{ language }, filters, content, user] = await Promise.all([
        params,
        searchParams,
        fetchGamesContent(),
        getCurrentUser(),
    ]);

    return <GamesView content={content} page={languagePage(content, language)} user={user} searchParams={filters} />;
}
