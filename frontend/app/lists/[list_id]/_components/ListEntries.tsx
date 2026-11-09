"use client";

import { useState } from "react";
import { ProgressLink as Link } from "../../../_components/ProgressLink";
import { useRouter } from "next/navigation";

import type { ListLabel } from "../../../_components/LabelChip";
import { Pagination, PaginationLabels } from "../../../_components/Pagination";
import { StreamerStats, StreamerStatsData } from "../../../_components/StreamerStats";
import type { Paging } from "../../../_lib/paging";
import { EntryNote, EntryNoteLabels } from "./EntryNote";

export type ListEntry = {
    id: number;
    description: string;
    added_at: string;
    // null once the streamer opted out: the entry shows anonymized, note kept.
    streamer: {
        login: string;
        display_name: string;
        // null when they have no recent streams in any language.
        stats: StreamerStatsData | null;
    } | null;
};

// One page of the list's entries: `page` is the one shown, which the API keeps in range.
export type ListDetail = Paging & {
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
    empty: string;
    empty_cta: string;
    view_profile: string;
    remove_btn: string;
    remove_confirm: string;
    remove_error: string;
    pagination: PaginationLabels;
    no_stats: string;
    removed: string;
    removed_note: string;
};

function readCookie(name: string): string {
    const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : "";
}

export function ListEntries({ list, labels }: { list: ListDetail; labels: ListEntriesLabels }) {
    const router = useRouter();
    // A removed entry goes at once, before the page has reloaded without it.
    const [removedIds, setRemovedIds] = useState<number[]>([]);
    const [removingId, setRemovingId] = useState<number | null>(null);
    const [removeErrorId, setRemoveErrorId] = useState<number | null>(null);
    const entries = list.entries.filter((entry) => !removedIds.includes(entry.id));
    // Numbered through the whole list, so page 2's first is #51.
    const firstNumber = (list.page - 1) * list.page_size + 1;

    async function handleRemove(entryId: number) {
        if (removingId !== null || !window.confirm(labels.remove_confirm)) return;
        setRemovingId(entryId);
        setRemoveErrorId(null);
        let removed = false;
        try {
            const response = await fetch(`/api/lists/${list.id}/entries/${entryId}/`, {
                method: "DELETE",
                credentials: "include",
                headers: { "X-CSRFToken": readCookie("csrftoken") },
            });
            // Already removed, e.g. in another tab, is as good as removed here.
            removed = response.ok || response.status === 404;
        } catch {
            removed = false;
        }
        setRemovingId(null);
        if (!removed) {
            setRemoveErrorId(entryId);
            return;
        }
        setRemovedIds((ids) => [...ids, entryId]);
        // The page header shows the streamer count too, and the next page's first entry
        // moves up into this one. A last page left empty shows the one before it.
        router.refresh();
    }

    if (entries.length === 0 && list.pages === 1) {
        return (
            <div className="border-t border-t-gray-400 pt-8">
                <p className="mb-8 text-gray-800">{labels.empty}</p>
                <Link href="/streamers" className="text-sm inline-block p-2 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 text-center border border-blue-600 hover:border-blue-700">
                    {labels.empty_cta}
                </Link>
            </div>
        );
    }

    return (
        <div>
            {entries.map((entry, index) => (
                <div key={entry.id} className="border-t border-t-gray-400 pt-2 mb-16 bg-white">
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 items-center pb-2 gap-6">
                        <div className="font-bold text-lg">
                            <span className="text-gray-500 font-normal mr-1">#{firstNumber + index} </span>
                            <span>{entry.streamer ? entry.streamer.display_name : labels.removed}</span>
                        </div>
                        <div className="flex flex-col md:flex-row lg:flex-row md:items-center justify-end gap-6">
                            {entry.streamer && (
                                <Link className="text-sm align-baseline inline-block p-1 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 text-center border border-blue-600 hover:border-blue-700"
                                    href={`/streamers/${entry.streamer.login}`} rel="nofollow" target="_blank" title="View streamer profile">{labels.view_profile}</Link>
                            )}
                            <button
                                type="button"
                                onClick={() => handleRemove(entry.id)}
                                // Only the one being removed greys out; handleRemove ignores
                                // clicks on the others until it's done.
                                disabled={removingId === entry.id}
                                className="text-sm p-1 bg-red-600 text-white font-medium rounded hover:bg-red-700 min-w-36 border border-red-600 hover:border-red-700 cursor-pointer disabled:bg-gray-400 disabled:border-gray-400 disabled:hover:bg-gray-400 disabled:hover:border-gray-400 disabled:cursor-not-allowed"
                            >
                                {labels.remove_btn}
                            </button>
                        </div>
                    </div>
                    {removeErrorId === entry.id && (
                        <p role="alert" className="pb-2 text-sm text-red-600">{labels.remove_error}</p>
                    )}

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

            <Pagination path={`/lists/${list.id}`} query="" page={list.page} pages={list.pages} labels={labels.pagination} />
        </div>
    );
}
