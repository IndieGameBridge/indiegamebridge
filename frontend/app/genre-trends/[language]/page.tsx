import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { getCurrentUser } from "../../_lib/auth";
import {
    GenreTrendsContent,
    GenreTrendsView,
    fetchGenreTrendsContent,
    genreTrendsMetadata,
} from "../_components/GenreTrendsView";

// Reads auth cookies (for the header) + live backend data per request, so never
// prerender at build time. Render on demand on the Worker.
export const dynamic = "force-dynamic";

type Props = { params: Promise<{ language: string }> };

// The language's page by its slug, e.g. "japanese"; any other slug is a 404, as is
// every slug while the cached payload predates the language pages.
function languagePage(content: GenreTrendsContent, slug: string) {
    const page = content.language_pages?.find((one) => one.slug === slug);
    if (!page) {
        notFound();
    }
    return page;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
    const { language } = await params;
    const content = await fetchGenreTrendsContent();
    return genreTrendsMetadata(content, languagePage(content, language));
}

export default async function GenreTrendsLanguagePage({ params }: Props) {
    const { language } = await params;
    const [content, user] = await Promise.all([
        fetchGenreTrendsContent(),
        getCurrentUser(),
    ]);

    return <GenreTrendsView content={content} page={languagePage(content, language)} user={user} />;
}
