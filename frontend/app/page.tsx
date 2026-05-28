import { Fragment } from "react/jsx-runtime";
import type { Metadata } from "next";
import {
    SearchStreamerForm,
    SearchStreamerResultsList,
    SearchFormData,
    StreamerData,
    StreamersDistribution,
    PageHeader,
    PageFooter,
    PageFooterContent
} from "./_components";
import { getCurrentUser } from "./_lib/auth";
import { serverFetch } from "./_lib/server-fetch";

type Section = {
    title: string;
    description: string;
};

type FeaturedSection = {
    title: string;
    description: string;
    features: string[];
};

type HomePageContent = {
    title: string;
    description: string;
    info: string;
    project_goal: Section;
    search_form: SearchFormData;
    search_results_title: string;
    search_results: StreamerData[];
    methodology: Section;
    roadmap: FeaturedSection;
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
    };
}

export default async function Home() {
    const [content, user] = await Promise.all([
        fetchHomeContent(),
        getCurrentUser(),
    ]);

    return (
        <Fragment>
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
                        <h2 className="text-2xl font-bold mb-4">{content.project_goal.title}</h2>
                        <p>{content.project_goal.description}</p>
                    </div>
                </section>

                {/* Streamer Peak-Viewer Distribution */}
                <StreamersDistribution />

                {/* Demo Search */}
                <section className="border-t border-gray-400 px-6">
                    <div className="max-w-[1000] mx-auto pt-24">
                        <h2 className="text-2xl font-bold mb-4">{content.search_form.title}</h2>
                        <SearchStreamerForm search_form={content.search_form} user={user}></SearchStreamerForm>
                        <SearchStreamerResultsList search_results={content.search_results} search_results_title={content.search_results_title}></SearchStreamerResultsList>
                    </div>
                </section>

                {/* Methodology */}
                <section className="border-t border-gray-400 px-6">
                    <div className="max-w-[1000] mx-auto pt-24 pb-12">
                        <h2 className="text-2xl font-bold mb-4">{content.methodology.title}</h2>
                        <p>{content.methodology.description}</p>
                    </div>
                </section>

                {/* Roadmap */}
                <section className="px-6">
                    <div className="max-w-[1000] mx-auto pt-12 pb-24">
                        <h2 className="text-2xl font-bold mb-4">{content.roadmap.title}</h2>
                        <p className="pb-2">{content.roadmap.description}</p>
                        <ul className="list-disc pl-5">
                            {content.roadmap.features.map((feature, index) => (
                                <li key={"coming-feature-" + index} className="py-2">{feature}</li>
                            ))}
                        </ul>
                    </div>
                </section>
            </main>

            <PageFooter content={content.footer_content} />
        </Fragment>
    );
}
