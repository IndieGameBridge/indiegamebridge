import { Fragment } from "react/jsx-runtime";
import type { Metadata } from "next";

import {
    FaqContent,
    LanguageSwitch,
    PageFooter,
    PageFooterContent,
    PageHeader,
    Standouts,
    StandoutsContent,
} from "../../_components";
import type { CurrentUser } from "../../_lib/auth";
import { RESULTS_ANCHOR, pageParam } from "../../_lib/paging";
import { serverFetch } from "../../_lib/server-fetch";
import { SHARED_OPEN_GRAPH, SHARED_TWITTER } from "../../_lib/share-metadata";
import { GamesGuide, GamesGuideCopy } from "./GamesGuide";
import { GamesList } from "./GamesList";
import { GamesSearchForm, GamesSearchFormData } from "./GamesSearchForm";
import type { GameLanguage, GameListLabels, GameSearchResponse } from "./types";

// A page's own copy: the overview's sits at the top of the payload, each language's in
// language_pages.
type PageCopy = {
    title: string;
    description: string;
    seo_title: string;
    seo_description: string;
    intro: string;
    // Says when a page's charts cover less than 4 weeks, for a language collected since lately.
    note: string | null;
};

export type GamesLanguagePage = PageCopy & GameLanguage & {
    slug: string;
    // Its most streamed games against the other languages. Null while it has too few days to
    // compare, and missing from a payload cached before it existed.
    standouts?: StandoutsContent | null;
};

export type GamesContent = PageCopy & {
    language_pages: GamesLanguagePage[];
    search_form: GamesSearchFormData;
    labels: GameListLabels;
    // Missing from a payload cached before they existed: the pages then show without them.
    guide?: GamesGuideCopy;
    faq?: FaqContent;
    footer_content: PageFooterContent;
};

export type GamesSearchParams = { [key: string]: string | string[] | undefined };

export async function fetchGamesContent(): Promise<GamesContent> {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const response = await serverFetch(`${apiBase}/pages/games/`);

    if (!response.ok) {
        throw new Error(`Failed to load games page content (status ${response.status})`);
    }

    return await response.json();
}

function pathOf(page: GamesLanguagePage | null): string {
    return page ? `/games/${page.slug}` : "/games";
}

export function gamesMetadata(content: GamesContent, page: GamesLanguagePage | null): Metadata {
    const copy = page ?? content;
    return {
        title: copy.seo_title,
        description: copy.seo_description,
        // The filters narrow one page rather than make new ones.
        alternates: { canonical: pathOf(page) },
        openGraph: {
            ...SHARED_OPEN_GRAPH,
            title: copy.seo_title,
            description: copy.seo_description,
            url: pathOf(page),
        },
        twitter: {
            ...SHARED_TWITTER,
            title: copy.seo_title,
            description: copy.seo_description,
        },
    };
}

function one(value: string | string[] | undefined): string | undefined {
    return Array.isArray(value) ? value[0] : value;
}

/** The form's filters in the page's address, as a query string for its links and the search. */
function filtersQuery(content: GamesContent, searchParams: GamesSearchParams): string {
    const params = new URLSearchParams();
    for (const one_filter of content.search_form.filters) {
        const value = one(searchParams[one_filter.name]);
        if (value !== undefined) params.set(one_filter.name, value);
    }
    return params.toString();
}

async function searchGames(apiQuery: string): Promise<GameSearchResponse> {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const response = await serverFetch(`${apiBase}/games/?${apiQuery}`);

    if (!response.ok) {
        throw new Error(`Failed to run game search (status ${response.status})`);
    }

    return await response.json();
}

/**
 * A Games page: the overview, which adds every language up, when `page` is null, or one
 * language's own page.
 */
export async function GamesView({ content, page, user, searchParams }: {
    content: GamesContent;
    page: GamesLanguagePage | null;
    user: CurrentUser | null;
    searchParams: GamesSearchParams;
}) {
    const copy = page ?? content;
    const query = filtersQuery(content, searchParams);
    // The list the filters pick; the page of it shown is asked for on top.
    const listQuery = [`lang=${page?.code ?? "all"}`, query].filter(Boolean).join("&");
    const resultsPage = pageParam(searchParams.p);
    const search = await searchGames(resultsPage ? `${listQuery}&p=${encodeURIComponent(resultsPage)}` : listQuery);
    // The questions are the overview's: Google wants one marked-up copy of them, not one per
    // language page.
    const faq = !page && content.faq && content.faq.items.length > 0 ? content.faq : null;

    return (
        <Fragment>
            <PageHeader user={user} title={copy.title} description={copy.description} />

            <main className="w-full">
                <section className="px-6">
                    <div className="max-w-[1000] mx-auto pt-24 pb-24">
                        <p className="mb-8">{copy.intro}</p>
                        {copy.note && (
                            <p className="mb-8 text-sm border-l-4 border-gray-300 pl-4">{copy.note}</p>
                        )}
                        {page?.standouts && <Standouts standouts={page.standouts} />}
                        <LanguageSwitch base="/games" pages={content.language_pages} current={page?.slug ?? null} query={query} />
                        <GamesSearchForm
                            key={`${pathOf(page)}?${query}`}
                            search_form={content.search_form}
                            path={pathOf(page)}
                            initial_values={searchParams}
                        />
                        <div id={RESULTS_ANCHOR} className="scroll-mt-8">
                            {/* Keyed by the list: new filters start it afresh, while another page
                                of the same list keeps the chart's language as picked. */}
                            <GamesList
                                key={listQuery}
                                results={search.results}
                                total={search.total}
                                paging={{ page: search.page, pages: search.pages, page_size: search.page_size }}
                                newest_hour={search.newest_hour}
                                path={pathOf(page)}
                                query={query}
                                peak={one(searchParams.peak) ?? "any"}
                                languages={content.language_pages.map(({ code, label, since_hour }) => ({ code, label, since_hour }))}
                                default_language={page?.code ?? "all"}
                                labels={content.labels}
                            />
                        </div>
                    </div>
                </section>

                {/* The list comes first; how to read it is here for whoever wants it. */}
                {content.guide && (
                    <section className="border-t border-gray-400 px-6">
                        <div className="max-w-[1000] mx-auto py-24">
                            <GamesGuide guide={content.guide} faq={faq} />
                        </div>
                    </section>
                )}
            </main>

            <PageFooter content={content.footer_content} />
        </Fragment>
    );
}
