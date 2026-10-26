"use client";

import { Fragment, useEffect, useState } from "react";
import Link from "next/link";

import { messageFrom } from "../../_components/ListForm";

export type AddSearchToListLabels = {
    list_label: string;
    list_placeholder: string;
    note: string;
    submit_btn: string;
    saving: string;
    cancel_btn: string;
    loading: string;
    load_error: string;
    no_lists: string;
    error: string;
    done: string;
    done_skipped: string;
    open_list: string;
    close_btn: string;
};

type ListChoice = { id: number; title: string; streamers_count: number };

type Added = { listId: number; title: string; added: number; skipped: number };

function readCookie(name: string): string {
    const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : "";
}

// Adds every streamer a search found to one of the user's lists, after the
// ones already in it, then says how many were new.
export function AddSearchToList({ search_query, labels, onClose }: {
    search_query: string;
    labels: AddSearchToListLabels;
    onClose: () => void;
}) {
    const [lists, setLists] = useState<ListChoice[] | null>(null);
    const [loadError, setLoadError] = useState(false);
    const [listId, setListId] = useState("");
    const [pending, setPending] = useState(false);
    const [error, setError] = useState("");
    const [added, setAdded] = useState<Added | null>(null);

    useEffect(() => {
        let ignore = false;
        async function loadLists() {
            try {
                const response = await fetch("/api/lists/", { credentials: "include" });
                if (!response.ok) {
                    throw new Error(`Lists request failed (status ${response.status})`);
                }
                const data: { lists: ListChoice[] } = await response.json();
                if (!ignore) setLists(data.lists);
            } catch {
                if (!ignore) setLoadError(true);
            }
        }
        loadLists();
        return () => {
            ignore = true;
        };
    }, []);

    async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const chosen = lists?.find((one_list) => String(one_list.id) === listId);
        if (pending || !chosen) return;
        setPending(true);
        setError("");
        try {
            const response = await fetch(`/api/lists/${chosen.id}/entries/`, {
                method: "POST",
                credentials: "include",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": readCookie("csrftoken"),
                },
                // Re-run by the backend, like saving the search as a new list.
                body: JSON.stringify({ search: search_query }),
            });
            if (response.ok) {
                const result: { added: number; already_in_list: number } = await response.json();
                setAdded({ listId: chosen.id, title: chosen.title, added: result.added, skipped: result.already_in_list });
                return;
            }
            // A 400 says why, e.g. the list would grow past its cap.
            const payload = response.status === 400 ? await response.json() : null;
            setError(messageFrom(payload) ?? labels.error);
        } catch {
            setError(labels.error);
        }
        setPending(false);
    }

    if (added) {
        const message = (added.skipped > 0 ? labels.done_skipped : labels.done)
            .replace("{title}", added.title)
            .replace("{added}", added.added.toLocaleString())
            .replace("{skipped}", added.skipped.toLocaleString());
        return (
            <div role="status" className="basis-full text-sm flex flex-row flex-wrap items-center gap-6 border-t border-t-gray-400 pt-4">
                <p>{message}</p>
                <Link
                    href={`/lists/${added.listId}`}
                    className="text-sm p-2 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 text-center border border-blue-600 hover:border-blue-700"
                >
                    {labels.open_list}
                </Link>
                <button type="button" onClick={onClose} className="text-blue-700 hover:underline cursor-pointer">
                    {labels.close_btn}
                </button>
            </div>
        );
    }

    const hasLists = lists !== null && lists.length > 0;
    return (
        <form
            onSubmit={handleSubmit}
            aria-label={labels.submit_btn}
            className="basis-full text-sm grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4 border-t border-t-gray-400 pt-4"
        >
            {lists === null && !loadError && <p className="md:col-span-2 text-gray-600">{labels.loading}</p>}
            {loadError && <p role="alert" className="md:col-span-2 text-red-600">{labels.load_error}</p>}
            {lists?.length === 0 && <p className="md:col-span-2">{labels.no_lists}</p>}
            {hasLists && (
                <Fragment>
                    <div className="flex flex-col gap-1">
                        <label htmlFor="add-results-list" className="text-brand-blue">{labels.list_label}</label>
                        <select
                            id="add-results-list"
                            required
                            autoFocus
                            value={listId}
                            onChange={(e) => setListId(e.target.value)}
                            className="p-2 border border-gray-300 rounded-sm outline-gray-400 bg-white"
                        >
                            <option value="" disabled>{labels.list_placeholder}</option>
                            {lists.map((one_list) => (
                                <option key={one_list.id} value={one_list.id}>
                                    {one_list.title} ({one_list.streamers_count.toLocaleString()})
                                </option>
                            ))}
                        </select>
                    </div>
                    <p className="md:col-span-2 italic">{labels.note}</p>
                </Fragment>
            )}
            {error && <p role="alert" className="md:col-span-2 text-red-600">{error}</p>}
            <div className="md:col-span-2 flex flex-row items-center gap-6">
                {hasLists && (
                    <button
                        type="submit"
                        disabled={pending}
                        className="text-sm p-2 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 border border-blue-600 hover:border-blue-700 cursor-pointer disabled:bg-gray-400 disabled:border-gray-400 disabled:hover:bg-gray-400 disabled:hover:border-gray-400 disabled:cursor-not-allowed"
                    >
                        {pending ? labels.saving : labels.submit_btn}
                    </button>
                )}
                <button
                    type="button"
                    onClick={onClose}
                    disabled={pending}
                    className="text-blue-700 hover:underline cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed"
                >
                    {labels.cancel_btn}
                </button>
            </div>
        </form>
    );
}
