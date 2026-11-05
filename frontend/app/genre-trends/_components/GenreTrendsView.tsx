import { Fragment } from "react/jsx-runtime";
import type { Metadata } from "next";

import {
    FaqContent,
    FaqSection,
    GenreDiagram,
    GenreTrends,
    LanguageSwitch,
    PageHeader,
    PageFooter,
    PageFooterContent,
} from "../../_components";
import type { CurrentUser } from "../../_lib/auth";
import { jsonLd } from "../../_lib/json-ld";
import { serverFetch } from "../../_lib/server-fetch";

// A page's own copy: the overview's sits at the top of the payload, each language's
// in language_pages.
type PageCopy = {
    title: string;
    description: string;
    seo_title?: string;
    seo_description?: string;
    intro?: string;
    // Says when a page's numbers cover less than 4 weeks, for a language collected
    // since lately.
    note?: string | null;
};

export type GenreLanguagePage = PageCopy & {
    code: string;
    slug: string;
    label: string;
};

export type GenreTrendsContent = PageCopy & {
    faq?: FaqContent;
    // The 4 weeks the numbers cover; null until the stats have first been built.
    window?: { start: string; end: string; computed_at: string } | null;
    // Missing from a payload cached before the language pages existed, until
    // update_cached_pages rebuilds it: the overview then shows without the switch.
    language_pages?: GenreLanguagePage[];
    // What readers may do with the numbers; the structured data's license points at it.
    data_use: string;
    diagrams: GenreDiagram[];
    footer_content: PageFooterContent;
};

export async function fetchGenreTrendsContent(): Promise<GenreTrendsContent> {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const response = await serverFetch(`${apiBase}/pages/genre_trends/`);

    if (!response.ok) {
        throw new Error(`Failed to load genre trends page content (status ${response.status})`);
    }

    return await response.json();
}

function pathOf(page: GenreLanguagePage | null): string {
    return page ? `/genre-trends/${page.slug}` : "/genre-trends";
}

export function genreTrendsMetadata(content: GenreTrendsContent, page: GenreLanguagePage | null): Metadata {
    const copy = page ?? content;
    // Prefer the keyword-led SEO copy; fall back to the visible header text.
    const seoTitle = copy.seo_title ?? copy.title;
    const seoDescription = copy.seo_description ?? copy.description;
    return {
        title: seoTitle,
        description: seoDescription,
        alternates: { canonical: pathOf(page) },
        openGraph: {
            title: seoTitle,
            description: seoDescription,
            url: pathOf(page),
        },
        twitter: {
            title: seoTitle,
            description: seoDescription,
        },
    };
}

/**
 * A Genre Trends page: the overview, which adds every language up, when `page` is
 * null, or one language's own page.
 */
export function GenreTrendsView({ content, page, user }: {
    content: GenreTrendsContent;
    page: GenreLanguagePage | null;
    user: CurrentUser | null;
}) {
    const copy = page ?? content;
    const siteUrl = process.env.FRONTEND_URL ?? "http://localhost:3000";

    // Describes the page's numbers as a dataset, for Google Dataset Search and other
    // crawlers. Absolute URLs, since structured data isn't resolved against the page.
    const datasetJsonLd = content.window
        ? {
            "@context": "https://schema.org",
            "@type": "Dataset",
            name: page ? `Twitch game genre trends in ${page.label}` : "Twitch game genre trends",
            description: copy.seo_description ?? copy.description,
            url: `${siteUrl}${pathOf(page)}`,
            creator: {
                "@type": "Organization",
                name: "IndieGameBridge",
                url: siteUrl,
            },
            isAccessibleForFree: true,
            // A notice that grants nothing, not an open license: Twitch's developer agreement
            // forbids licensing data built from its API.
            license: {
                "@type": "CreativeWork",
                name: "Data use notice",
                url: `${siteUrl}${pathOf(page)}#data-use`,
            },
            temporalCoverage: `${content.window.start}/${content.window.end}`,
            dateModified: content.window.computed_at,
            variableMeasured: content.diagrams.map((diagram) => diagram.title),
        }
        : null;

    // The FAQ is the overview's: Google wants one marked-up instance of an FAQ per
    // site, not one per page that repeats it.
    const faq = !page && content.faq && content.faq.items.length > 0 ? content.faq : null;

    return (
        <Fragment>
            {datasetJsonLd && (
                <script
                    type="application/ld+json"
                    dangerouslySetInnerHTML={{ __html: jsonLd(datasetJsonLd) }}
                />
            )}
            <PageHeader
                user={user}
                title={copy.title}
                description={copy.description}
            />

            <main className="w-full">
                <section className="px-6">
                    <div className="max-w-[1000] mx-auto pt-24 pb-24">
                        {copy.intro && (
                            <p className="mb-8">{copy.intro}</p>
                        )}
                        {copy.note && (
                            <p className="mb-8 text-sm border-l-4 border-gray-300 pl-4">{copy.note}</p>
                        )}
                        {content.language_pages && (
                            <LanguageSwitch base="/genre-trends" pages={content.language_pages} current={page?.slug ?? null} />
                        )}
                        <GenreTrends
                            diagrams={content.diagrams}
                            language={page ? { code: page.code, label: page.label } : null}
                        />
                        <p id="data-use" className="mt-16 text-sm text-gray-600">{content.data_use}</p>
                        {faq && <FaqSection faq={faq} />}
                    </div>
                </section>
            </main>

            <PageFooter content={content.footer_content} />
        </Fragment>
    );
}
