import { Fragment } from "react/jsx-runtime";
import type { Metadata } from "next";

import { LanguageSwitch, PageFooter, PageFooterContent, PageHeader } from "../../_components";
import type { CurrentUser } from "../../_lib/auth";
import { serverFetch } from "../../_lib/server-fetch";
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

export type GamesLanguagePage = PageCopy & GameLanguage & { slug: string };

export type GamesContent = PageCopy & {
    language_pages: GamesLanguagePage[];
    search_form: GamesSearchFormData;
    labels: GameListLabels;
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
            title: copy.seo_title,
            description: copy.seo_description,
            url: pathOf(page),
        },
        twitter: {
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
    const apiQuery = [`lang=${page?.code ?? "all"}`, query].filter(Boolean).join("&");
    const search = await searchGames(apiQuery);

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
                        <LanguageSwitch base="/games" pages={content.language_pages} current={page?.slug ?? null} query={query} />
                        <GamesSearchForm
                            key={`${pathOf(page)}?${query}`}
                            search_form={content.search_form}
                            path={pathOf(page)}
                            initial_values={searchParams}
                        />
                        <GamesList
                            key={apiQuery}
                            results={search.results}
                            total={search.total}
                            newest_hour={search.newest_hour}
                            api_query={apiQuery}
                            peak={one(searchParams.peak) ?? "any"}
                            languages={content.language_pages.map(({ code, label, since_hour }) => ({ code, label, since_hour }))}
                            default_language={page?.code ?? "all"}
                            labels={content.labels}
                        />
                    </div>
                </section>
            </main>

            <PageFooter content={content.footer_content} />
        </Fragment>
    );
}
