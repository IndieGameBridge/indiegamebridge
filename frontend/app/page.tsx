import { Fragment } from "react/jsx-runtime";
import type { Metadata } from "next";
import {
    SearchStreamerForm,
    SearchStreamerResultsList,
    SearchFormData,
    StreamerData,
    ResultsListLabels,
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
    info: string;
    project_goal: Section;
    search_form: SearchFormData;
    search_results: StreamerData[];
    search_total: number;
    methodology: Section;
    results_labels: ResultsListLabels;
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
    return {
        title: content.title,
        description: content.description,
        alternates: { canonical: "/" },
        openGraph: {
            title: content.title,
            description: content.description,
            url: "/",
        },
        twitter: {
            title: content.title,
            description: content.description,
        },
    };
}

export default async function Home() {
    const [content, user] = await Promise.all([
        fetchHomeContent(),
        getCurrentUser(),
    ]);

    const siteUrl = process.env.FRONTEND_URL ?? "http://localhost:3000";
    const jsonLd = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        name: "IndieGameBridge",
        url: siteUrl,
        description: content.description,
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
            />

            {/* Main */}
            <main className="w-full">

                {/* Project Goal */}
                <section className="px-6">
                    <div className="max-w-[1000] mx-auto pt-24 pb-12">
                        <h2 className="text-2xl font-bold mb-8">{content.project_goal.title}</h2>
                        <p>{content.project_goal.description}</p>
                    </div>
                </section>

                {/* Streamer Peak-Viewer Distribution */}
                <StreamersDistribution />

                {/* Demo Search */}
                <section className="border-t border-gray-400 px-6">
                    <div className="max-w-[1000] mx-auto pt-24 pb-24">
                        <h2 className="text-2xl font-bold mb-8">{content.search_form.title}</h2>
                        <SearchStreamerForm search_form={content.search_form} user={user}></SearchStreamerForm>
                        <SearchStreamerResultsList
                            search_results={content.search_results}
                            labels={content.results_labels}
                            total={content.search_total}
                            more_href={user ? "/streamers" : `/login?next=${encodeURIComponent("/streamers")}`}
                        ></SearchStreamerResultsList>
                    </div>
                </section>

                {/* Methodology */}
                <section className="border-t border-gray-400 px-6">
                    <div className="max-w-[1000] mx-auto pt-24 pb-24">
                        <h2 className="text-2xl font-bold mb-8">{content.methodology.title}</h2>
                        <p>{content.methodology.description}</p>
                    </div>
                </section>
            </main>

            <PageFooter content={content.footer_content} />
        </Fragment>
    );
}
