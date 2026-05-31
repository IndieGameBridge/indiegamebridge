"use client";

import { useState } from "react";
import Link from "next/link";

import { loadStreamersPage } from "../streamers/actions";

export type StreamerData = {
    login: string;
    display_name: string;
    streams_count: number;
    total_duration: string;
    peak_viewers: number;
    avg_viewers: number;
    games: string[];
};

type Props = {
    search_results: StreamerData[];
    total?: number;
    can_load_more?: boolean;
    more_href?: string;
};

export function SearchStreamerResultsList({
    search_results,
    total,
    can_load_more = false,
    more_href,
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
            {loadedResults.map((one_result, index) => (
                <div key={`search-result-${index}`} className="border-t border-t-gray-400 pt-4 mb-24 bg-white">
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 items-center pb-4 gap-6">
                        <div className="font-bold text-lg"><span className="text-gray-500 font-normal">#{index + 1} </span><span>{one_result.display_name}</span></div>
                        <div className="flex flex-col md:flex-row lg:flex-row justify-end gap-6">
                            <Link className="text-sm align-baseline inline-block p-2 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 text-center border border-blue-600 hover:border-blue-700"
                                href={`/streamers/${one_result.login}`} rel="nofollow" target="_blank" title="View streamer profile">View Profile</Link>
                        </div>
                    </div>
                    <div className="border-gray-300 border-t pt-4 text-sm">
                        <div className="mb-4">
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                <div className="col-span-1 md:col-span-1 lg:col-span-2 grid grid-cols-1 md:grid-cols-1 lg:grid-cols-2 gap-4">
                                    <div className="text-nowrap">Peak {one_result.peak_viewers.toLocaleString()}</div>
                                    <div className="text-nowrap">Avg {one_result.avg_viewers.toLocaleString()}</div>
                                </div>
                                <div className="text-nowrap">{one_result.streams_count.toLocaleString()} {one_result.streams_count > 1 ? 'streams' : 'stream'} • {one_result.total_duration}</div>
                            </div>
                        </div>
                        <div className="flex flex-row gap-x-2 gap-y-2 flex-wrap">{
                            one_result.games.map((game_name, game_index) => (
                                <div key={`streamer-game-${game_index}`} className="py-1 px-2 rounded-sm bg-gray-200">{game_name}</div>
                            ))
                        }</div>
                    </div>
                </div>
            ))}
            {hasMore && (
                <div className="text-center">
                    <button
                        type="button"
                        onClick={handleShowMore}
                        disabled={loading}
                        className="text-sm inline-block p-2 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 border border-blue-600 hover:border-blue-700 cursor-pointer disabled:bg-gray-400 disabled:border-gray-400 disabled:hover:bg-gray-400 disabled:hover:border-gray-400 disabled:cursor-not-allowed"
                    >
                        Show More
                    </button>
                    {loading && (
                        <div className="pt-2 text-sm text-gray-600">Loading...</div>
                    )}
                </div>
            )}
            {more_href && (
                <div className="text-center">
                    <Link
                        href={more_href}
                        className="text-sm inline-block p-2 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 border border-blue-600 hover:border-blue-700 cursor-pointer"
                    >
                        Show More
                    </Link>
                </div>
            )}
        </div>
    );
};
