import { Suspense } from "react";
import { Fragment } from "react/jsx-runtime";
import type { Metadata } from "next";
import { cookies } from "next/headers";

import {
    AddToListLabels,
    SearchStreamerForm,
    SearchStreamerResultsList,
    SearchFormData,
    StreamerData,
    ResultsListLabels,
    PageHeader,
    PageFooter,
    PageFooterContent,
} from "../_components";
import { ExportMenu, ExportMenuLabels } from "../_components/ExportMenu";
import { CurrentUser, getCurrentUser } from "../_lib/auth";
import { Paging, RESULTS_ANCHOR, pageParam } from "../_lib/paging";
import { serverFetch } from "../_lib/server-fetch";
import { LoadingNote } from "./_components/LoadingNote";
import { PublicPageCopy, PublicStreamers } from "./_components/PublicStreamers";
import { SaveSearchAsList, SaveListLabels } from "./_components/SaveSearchAsList";
import { StreamersGuide } from "./_components/StreamersGuide";

// Reads auth cookies + live backend data per request, so never prerender at
// build time (the backend isn't reachable then). Render on demand on the Worker.
export const dynamic = "force-dynamic";

type StreamersPageContent = {
    title: string;
    description: string;
    seo_title: string;
    seo_description: string;
    public_page: PublicPageCopy;
    search_form: SearchFormData;
    search_results: StreamerData[];
    search_total: number;
    results_labels: ResultsListLabels;
    add_to_list: AddToListLabels;
    save_list: SaveListLabels;
    // Absent until the page's cached text is rebuilt with it.
    export?: ExportMenuLabels;
    footer_content: PageFooterContent;
};

type SearchResponse = Paging & {
    filters: Record<string, unknown>;
    results: StreamerData[];
    total: number;
};

async function fetchStreamersContent(): Promise<StreamersPageContent> {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const response = await serverFetch(`${apiBase}/pages/streamers/`);

    if (!response.ok) {
        throw new Error(`Failed to load streamers page content (status ${response.status})`);
    }

    return await response.json();
}

export async function generateMetadata(): Promise<Metadata> {
    const content = await fetchStreamersContent();
    return {
        title: content.seo_title,
        description: content.seo_description,
        // A search's URL shows a logged-out visitor this same page, so it points here too.
        alternates: { canonical: "/streamers" },
        openGraph: {
            title: content.seo_title,
            description: content.seo_description,
            url: "/streamers",
        },
        twitter: {
            title: content.seo_title,
            description: content.seo_description,
        },
    };
}

// The search's filters from the address. The page isn't one: it stays out of the export, a
// saved list and the key that starts a new search afresh.
function buildSearchQuery(searchParams: { [key: string]: string | string[] | undefined }): string {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(searchParams)) {
        if (value === undefined || key === "p") continue;
        if (Array.isArray(value)) {
            for (const v of value) params.append(key, v);
        } else {
            params.append(key, value);
        }
    }
    return params.toString();
}

// The results of a logged-in user's search. On its own under a Suspense boundary, so the
// spinner belongs to the search alone: a logged-out visitor's page streams nothing and
// arrives whole.
async function SearchResults({ content, user, searchQuery, page }: {
    content: StreamersPageContent;
    user: CurrentUser;
    searchQuery: string;
    page: string | undefined;
}) {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const apiParams = new URLSearchParams(searchQuery);
    if (page) apiParams.set("p", page);
    const apiQuery = apiParams.toString();
    // The user's own cookies, so the search counts as theirs: recorded for them when they
    // allow tracking, and rate-limited per user rather than per address.
    const cookieHeader = (await cookies()).toString();
    const searchResp = await serverFetch(`${apiBase}/streamers/${apiQuery ? `?${apiQuery}` : ""}`, {
        headers: { cookie: cookieHeader },
        cache: "no-store",
    });

    if (!searchResp.ok) {
        throw new Error(`Failed to run streamer search (status ${searchResp.status})`);
    }

    const search: SearchResponse = await searchResp.json();

    return (
        <SearchStreamerResultsList
            search_results={search.results}
            user={user}
            labels={content.results_labels}
            total={search.total}
            paging={{ page: search.page, pages: search.pages, page_size: search.page_size, query: searchQuery }}
            add_to_list={content.add_to_list}
            count_actions={search.total > 0
                ? (
                    <div className="w-full md:w-auto flex flex-col md:flex-row md:items-start gap-6">
                        {content.export && (
                            <ExportMenu url="/api/streamers/export/" query={searchQuery} labels={content.export} />
                        )}
                        <SaveSearchAsList search_query={searchQuery} labels={content.save_list} />
                    </div>
                )
                : undefined}
        />
    );
}

export default async function StreamersPage({
    searchParams,
}: {
    searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
    const [user, content, sp] = await Promise.all([
        getCurrentUser(),
        fetchStreamersContent(),
        searchParams,
    ]);

    if (!user) {
        return (
            <PublicStreamers
                copy={content.public_page}
                search_form={content.search_form}
                search_results={content.search_results}
                search_total={content.search_total}
                results_labels={content.results_labels}
                footer_content={content.footer_content}
            />
        );
    }

    const searchQuery = buildSearchQuery(sp);

    return (
        <Fragment>
            <PageHeader user={user} title={content.title} description={content.description} />

            <main className="w-full">
                <section className="px-6">
                    <div className="max-w-[1000] mx-auto py-24">
                        {/* Keyed so each search starts fresh: the form takes its URL's filters,
                            going back included, and the spinner shows while the results load.
                            Another page of the same search keeps both, and its results replace
                            these once they've loaded, under the progress bar. */}
                        <Fragment key={searchQuery}>
                            <SearchStreamerForm
                                search_form={content.search_form}
                                user={user}
                                initial_values={sp}
                            />
                            <div id={RESULTS_ANCHOR} className="scroll-mt-8" />
                            <Suspense
                                fallback={<LoadingNote text="Searching streamers…" />}
                            >
                                <SearchResults content={content} user={user} searchQuery={searchQuery} page={pageParam(sp.p)} />
                            </Suspense>
                        </Fragment>
                    </div>
                </section>

                {/* The search comes first; the page's guide is here for whoever wants it. */}
                <section className="border-t border-gray-400 px-6">
                    <div className="max-w-[1000] mx-auto py-24">
                        <StreamersGuide copy={content.public_page} logged_in />
                    </div>
                </section>
            </main>

            <PageFooter content={content.footer_content} />
        </Fragment>
    );
}
