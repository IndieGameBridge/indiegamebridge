import { Fragment } from "react/jsx-runtime";
import type { Metadata } from "next";

import {
    GenreTrends,
    GenreDiagram,
    PageHeader,
    PageFooter,
    PageFooterContent,
} from "../_components";
import { getCurrentUser } from "../_lib/auth";
import { serverFetch } from "../_lib/server-fetch";

// Reads auth cookies (for the header) + live backend data per request, so never
// prerender at build time. Render on demand on the Worker.
export const dynamic = "force-dynamic";

type GenreTrendsContent = {
    title: string;
    description: string;
    diagrams: GenreDiagram[];
    footer_content: PageFooterContent;
};

async function fetchGenreTrendsContent(): Promise<GenreTrendsContent> {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const response = await serverFetch(`${apiBase}/pages/genre_trends/`);

    if (!response.ok) {
        throw new Error(`Failed to load genre trends page content (status ${response.status})`);
    }

    return await response.json();
}

export async function generateMetadata(): Promise<Metadata> {
    const content = await fetchGenreTrendsContent();
    return {
        title: content.title,
        description: content.description,
        alternates: { canonical: "/genre-trends" },
        openGraph: {
            title: content.title,
            description: content.description,
            url: "/genre-trends",
        },
        twitter: {
            title: content.title,
            description: content.description,
        },
    };
}

export default async function GenreTrendsPage() {
    const [content, user] = await Promise.all([
        fetchGenreTrendsContent(),
        getCurrentUser(),
    ]);

    return (
        <Fragment>
            <PageHeader
                user={user}
                title={content.title}
                description={content.description}
            />

            <main className="w-full">
                <section className="px-6">
                    <div className="max-w-[1000] mx-auto pt-24 pb-24">
                        <GenreTrends diagrams={content.diagrams} />
                    </div>
                </section>
            </main>

            <PageFooter content={content.footer_content} />
        </Fragment>
    );
}
