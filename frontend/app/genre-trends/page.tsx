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

type FaqItem = {
    question: string;
    answer: string;
};

type GenreTrendsContent = {
    title: string;
    description: string;
    seo_title?: string;
    seo_description?: string;
    intro?: string;
    faq?: {
        title: string;
        items: FaqItem[];
    };
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
    // Prefer the keyword-led SEO copy; fall back to the visible header text.
    const seoTitle = content.seo_title ?? content.title;
    const seoDescription = content.seo_description ?? content.description;
    return {
        title: seoTitle,
        description: seoDescription,
        alternates: { canonical: "/genre-trends" },
        openGraph: {
            title: seoTitle,
            description: seoDescription,
            url: "/genre-trends",
        },
        twitter: {
            title: seoTitle,
            description: seoDescription,
        },
    };
}

export default async function GenreTrendsPage() {
    const [content, user] = await Promise.all([
        fetchGenreTrendsContent(),
        getCurrentUser(),
    ]);

    const faqJsonLd = content.faq && content.faq.items.length > 0
        ? {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            mainEntity: content.faq.items.map((item) => ({
                "@type": "Question",
                name: item.question,
                acceptedAnswer: {
                    "@type": "Answer",
                    text: item.answer,
                },
            })),
        }
        : null;

    return (
        <Fragment>
            {faqJsonLd && (
                <script
                    type="application/ld+json"
                    dangerouslySetInnerHTML={{ __html: JSON.stringify(faqJsonLd) }}
                />
            )}
            <PageHeader
                user={user}
                title={content.title}
                description={content.description}
            />

            <main className="w-full">
                <section className="px-6">
                    <div className="max-w-[1000] mx-auto pt-24 pb-24">
                        {content.intro && (
                            <p className="mb-16 max-w-3xl text-lg opacity-80">{content.intro}</p>
                        )}
                        <GenreTrends diagrams={content.diagrams} />
                        {content.faq && content.faq.items.length > 0 && (
                            <section className="mt-24">
                                <h2 className="text-2xl font-bold mb-8">{content.faq.title}</h2>
                                <dl className="grid grid-cols-1 gap-8 max-w-3xl">
                                    {content.faq.items.map((item) => (
                                        <div key={item.question}>
                                            <dt className="font-semibold mb-2">{item.question}</dt>
                                            <dd className="opacity-80">{item.answer}</dd>
                                        </div>
                                    ))}
                                </dl>
                            </section>
                        )}
                    </div>
                </section>
            </main>

            <PageFooter content={content.footer_content} />
        </Fragment>
    );
}
