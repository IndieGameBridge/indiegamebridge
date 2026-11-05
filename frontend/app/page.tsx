import { Fragment } from "react/jsx-runtime";
import type { Metadata } from "next";
import {
    HomeHeaderButtons,
    HomeShowcase,
    HomeShowcaseContent,
    StreamersDistribution,
    PageHeader,
    PageFooter,
    PageFooterContent
} from "./_components";
import { getCurrentUser } from "./_lib/auth";
import { serverFetch } from "./_lib/server-fetch";

// Reads auth cookies + live backend data per request, so never prerender at
// build time (the backend isn't reachable then). Render on demand on the Worker.
export const dynamic = "force-dynamic";

type Section = {
    title: string;
    description: string;
};

type HomePageContent = {
    title: string;
    description: string;
    seo_title?: string;
    seo_description?: string;
    info: string;
    project_goal: Section;
    // Absent until the page's cached text is rebuilt with it.
    showcase?: HomeShowcaseContent;
    methodology: Section & { note?: string };
    footer_content: PageFooterContent;
};

async function fetchHomeContent(): Promise<HomePageContent> {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const response = await serverFetch(`${apiBase}/pages/home/`);

    if (!response.ok) {
        throw new Error(`Failed to load home page content (status ${response.status})`);
    }

    return await response.json();
}

export async function generateMetadata(): Promise<Metadata> {
    const content = await fetchHomeContent();
    // Prefer the keyword-led SEO copy; fall back to the visible header text.
    const seoTitle = content.seo_title ?? content.title;
    const seoDescription = content.seo_description ?? content.description;
    return {
        title: seoTitle,
        description: seoDescription,
        alternates: { canonical: "/" },
        openGraph: {
            title: seoTitle,
            description: seoDescription,
            url: "/",
        },
        twitter: {
            title: seoTitle,
            description: seoDescription,
        },
    };
}

export default async function Home() {
    const [content, user] = await Promise.all([
        fetchHomeContent(),
        getCurrentUser(),
    ]);

    const siteUrl = process.env.FRONTEND_URL ?? "http://localhost:3000";
    // No SearchAction: the only searchable content is the streamer pages, which
    // sit behind an OAuth gate and are deliberately kept out of the index.
    const jsonLd = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "@id": `${siteUrl}/#organization`,
                name: "IndieGameBridge",
                url: siteUrl,
            },
            {
                "@type": "WebSite",
                "@id": `${siteUrl}/#website`,
                name: "IndieGameBridge",
                url: siteUrl,
                description: content.description,
                publisher: { "@id": `${siteUrl}/#organization` },
            },
            {
                "@type": "WebApplication",
                "@id": `${siteUrl}/#app`,
                name: "IndieGameBridge",
                url: siteUrl,
                applicationCategory: "BusinessApplication",
                operatingSystem: "Web",
                description: content.description,
                publisher: { "@id": `${siteUrl}/#organization` },
            },
        ],
    };

    return (
        <Fragment>
            <script
                type="application/ld+json"
                dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
            />
            <PageHeader
                user={user}
                title={content.title}
                description={content.description}
                info={content.info}
                buttons={content.showcase && <HomeHeaderButtons labels={content.showcase.header_buttons} />}
            />

            {/* Main */}
            <main className="w-full">

                {/* Project Goal */}
                <section className="px-6">
                    <div className="max-w-[1000] mx-auto pt-18 pb-14">
                        <h2 className="text-2xl font-bold mb-6">{content.project_goal.title}</h2>
                        <p>{content.project_goal.description}</p>
                    </div>
                </section>

                {/* A block per feature */}
                {content.showcase && <HomeShowcase content={content.showcase} user={user} />}

                {/* Methodology */}
                <section className="border-t border-gray-400 px-6">
                    <div className="max-w-[1000] mx-auto pt-18 pb-4">
                        <h2 className="text-2xl font-bold mb-6">{content.methodology.title}</h2>
                        <p>{content.methodology.description}</p>
                        {content.methodology.note && <p className="mt-4">{content.methodology.note}</p>}
                    </div>
                </section>

                {/* Streamer Peak-Viewer Distribution */}
                <StreamersDistribution />
            </main>

            <PageFooter content={content.footer_content} />
        </Fragment>
    );
}
