import { Fragment } from "react/jsx-runtime";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import {
    SearchStreamerForm,
    SearchStreamerResultsList,
    SearchFormData,
    StreamerData,
    PageHeader,
    PageFooter,
    PageFooterContent,
} from "../_components";
import { getCurrentUser } from "../_lib/auth";

type StreamersPageContent = {
    search_form: SearchFormData;
    search_results_title: string;
    footer_content: PageFooterContent;
};

type SearchResponse = {
    filters: Record<string, unknown>;
    results: StreamerData[];
};

export const metadata: Metadata = {
    title: "Search Streamers — IndieGameBridge",
    robots: { index: false, follow: false },
};

function buildSearchQuery(searchParams: { [key: string]: string | string[] | undefined }): string {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(searchParams)) {
        if (value === undefined) continue;
        if (Array.isArray(value)) {
            for (const v of value) params.append(key, v);
        } else {
            params.append(key, value);
        }
    }
    return params.toString();
}

export default async function StreamersPage({
    searchParams,
}: {
    searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
    const user = await getCurrentUser();
    if (!user) {
        redirect(`/login?next=${encodeURIComponent("/streamers")}`);
    }

    const sp = await searchParams;
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const searchQuery = buildSearchQuery(sp);

    const [pageResp, searchResp] = await Promise.all([
        fetch(`${apiBase}/pages/home/`),
        fetch(`${apiBase}/streamers/search/${searchQuery ? `?${searchQuery}` : ""}`),
    ]);

    if (!pageResp.ok) {
        throw new Error(`Failed to load streamers page content (status ${pageResp.status})`);
    }
    if (!searchResp.ok) {
        throw new Error(`Failed to run streamer search (status ${searchResp.status})`);
    }

    const content: StreamersPageContent = await pageResp.json();
    const search: SearchResponse = await searchResp.json();

    return (
        <Fragment>
            <PageHeader user={user} />

            <main className="w-full">
                <section className="px-6">
                    <div className="max-w-[1000] mx-auto pt-16 pb-16">
                        <SearchStreamerForm
                            search_form={content.search_form}
                            user={user}
                            initial_values={sp}
                        />
                        <SearchStreamerResultsList
                            search_results={search.results}
                            search_results_title={content.search_results_title}
                        />
                    </div>
                </section>
            </main>

            <PageFooter content={content.footer_content} />
        </Fragment>
    );
}
