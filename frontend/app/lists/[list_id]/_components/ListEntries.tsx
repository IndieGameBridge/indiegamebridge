"use client";

import { useState } from "react";
import Link from "next/link";

import type { ListLabel } from "../../../_components/LabelChip";
import { StreamerStats, StreamerStatsData } from "../../../_components/StreamerStats";
import { EntryNote, EntryNoteLabels } from "./EntryNote";

export type ListEntry = {
    id: number;
    description: string;
    added_at: string;
    // null once the streamer opted out: the entry shows anonymized, note kept.
    streamer: {
        login: string;
        display_name: string;
        // null when they have no recent streams in the list's language.
        stats: StreamerStatsData | null;
    } | null;
};

export type ListDetail = {
    id: number;
    title: string;
    description: string;
    labels: ListLabel[];
    created_at: string;
    streamers_count: number;
    search: { label: string; value: string }[];
    entries: ListEntry[];
};

export type ListEntriesLabels = EntryNoteLabels & {
    view_profile: string;
    show_more: string;
    loading: string;
    load_error: string;
    no_stats: string;
    removed: string;
    removed_note: string;
};

export function ListEntries({ list, labels }: { list: ListDetail; labels: ListEntriesLabels }) {
    const [entries, setEntries] = useState<ListEntry[]>(list.entries);
    const [loadedPage, setLoadedPage] = useState(1);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const hasMore = entries.length < list.streamers_count;

    async function handleShowMore() {
        if (loading) return;
        const nextPage = loadedPage + 1;
        setLoading(true);
        setError("");
        try {
            const response = await fetch(`/api/lists/${list.id}/?p=${nextPage}`, { credentials: "include" });
            if (!response.ok) {
                throw new Error(`List page request failed (status ${response.status})`);
            }
            const data: ListDetail = await response.json();
            setEntries((prev) => [...prev, ...data.entries]);
            setLoadedPage(nextPage);
        } catch {
            setError(labels.load_error);
        } finally {
            setLoading(false);
        }
    }

    return (
        <div>
            {entries.map((entry, index) => (
                <div key={entry.id} className="border-t border-t-gray-400 pt-2 mb-16 bg-white">
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 items-center pb-2 gap-6">
                        <div className="font-bold text-lg">
                            <span className="text-gray-500 font-normal mr-1">#{index + 1} </span>
                            <span>{entry.streamer ? entry.streamer.display_name : labels.removed}</span>
                        </div>
                        {entry.streamer && (
                            <div className="flex flex-col md:flex-row lg:flex-row justify-end gap-6">
                                <Link className="text-sm align-baseline inline-block p-1 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 text-center border border-blue-600 hover:border-blue-700"
                                    href={`/streamers/${entry.streamer.login}`} rel="nofollow" target="_blank" title="View streamer profile">{labels.view_profile}</Link>
                            </div>
                        )}
                    </div>

                    {entry.streamer?.stats
                        ? <StreamerStats stats={entry.streamer.stats} />
                        : (
                            <p className="border-t border-t-gray-300 py-4 text-sm text-gray-600">
                                {entry.streamer ? labels.no_stats : labels.removed_note}
                            </p>
                        )}

                    <EntryNote listId={list.id} entryId={entry.id} initialNote={entry.description} labels={labels} />
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
                        {labels.show_more}
                    </button>
                    {loading && <div className="pt-2 text-sm text-gray-600">{labels.loading}</div>}
                    {error && <div role="alert" className="pt-2 text-sm text-red-600">{error}</div>}
                </div>
            )}
        </div>
    );
}
