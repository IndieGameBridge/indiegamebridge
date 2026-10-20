"use client";

import { Fragment, useState } from "react";
import Link from "next/link";

import { loadStreamersPage } from "../streamers/actions";
import { StreamerStats } from "./StreamerStats";

export type StreamerData = {
    login: string;
    display_name: string;
    streams_count: number;
    hours_streamed: number;
    peak_viewers: number;
    avg_viewers: number;
    genres: string[];
};

export type ResultsListLabels = {
    found_count?: string;
    view_profile: string;
    show_more: string;
    loading: string;
};

type Props = {
    search_results: StreamerData[];
    labels: ResultsListLabels;
    total?: number;
    can_load_more?: boolean;
    more_href?: string;
    // Shown beside the result count, e.g. the streamers page's "Save as list".
    count_actions?: React.ReactNode;
};

export function SearchStreamerResultsList({
    search_results,
    labels,
    total,
    can_load_more = false,
    more_href,
    count_actions,
}: Props) {
    const [loadedResults, setLoadedResults] = useState<StreamerData[]>(search_results);
    const [knownTotal, setKnownTotal] = useState<number>(total ?? search_results.length);
    const [loadedPage, setLoadedPage] = useState(1);
    const [loading, setLoading] = useState(false);
    const hasMore = can_load_more && loadedResults.length < knownTotal;

    async function handleShowMore() {
        if (loading) return;
        const nextPage = loadedPage + 1;
        setLoading(true);
        try {
            const data = await loadStreamersPage(window.location.search, nextPage);
            setLoadedResults((prev) => [...prev, ...data.results]);
            setKnownTotal(data.total);
            setLoadedPage(nextPage);
        } finally {
            setLoading(false);
        }
    }

    return (
        <div>
            {/* Result count, between the form and the listing; tracks Show More.
                Only shown when a real total is supplied (the home demo passes none). */}
            {total !== undefined && labels.found_count && (
                <div className="mb-8 flex flex-row flex-wrap items-center justify-between gap-4">
                    <div className="text-lg text-brand-blue">
                        {labels.found_count.replace("{count}", knownTotal.toLocaleString())}
                    </div>
                    {/* A Fragment's only child rather than a sibling in this row: an
                        element passed in from a server component can still be loading
                        here, and React then reports it as an unkeyed list item. */}
                    <Fragment>{count_actions}</Fragment>
                </div>
            )}

            {loadedResults.map((one_result, index) => (
                <div key={`search-result-${index}`} className="border-t border-t-gray-400 pt-2 mb-16 bg-white">

                    {/* Listing header */}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 items-center pb-2 gap-6">
                        <div className="font-bold text-lg"><span className="text-gray-500 font-normal mr-1">#{index + 1} </span><span>{one_result.display_name}</span></div>
                        <div className="flex flex-col md:flex-row lg:flex-row justify-end gap-6">
                            <Link className="text-sm align-baseline inline-block p-1 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 text-center border border-blue-600 hover:border-blue-700"
                                href={`/streamers/${one_result.login}`} rel="nofollow" target="_blank" title="View streamer profile">{labels.view_profile}</Link>
                        </div>
                    </div>

                    {/* Listing body */}
                    <StreamerStats stats={one_result} />
                </div>
            ))}

            {/* Show More */}
            {hasMore && (
                <div className="text-center">
                    <button
                        type="button"
                        onClick={handleShowMore}
                        disabled={loading}
                        className="text-sm inline-block p-2 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 border border-blue-600 hover:border-blue-700 cursor-pointer disabled:bg-gray-400 disabled:border-gray-400 disabled:hover:bg-gray-400 disabled:hover:border-gray-400 disabled:cursor-not-allowed"
                    >
                        {labels.show_more}
                    </button>
                    {loading && (
                        <div className="pt-2 text-sm text-gray-600">{labels.loading}</div>
                    )}
                </div>
            )}

            {/* Demo Show More leaads to target URL */}
            {more_href && (
                <div className="text-center">
                    <Link
                        href={more_href}
                        className="text-sm inline-block p-2 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 border border-blue-600 hover:border-blue-700 cursor-pointer"
                    >
                        {labels.show_more}
                    </Link>
                </div>
            )}
        </div>
    );
};
