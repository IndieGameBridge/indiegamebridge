"use client";

import { useId, useRef, useState } from "react";
import Link from "next/link";

import { messageFrom } from "./ListForm";
import { useDropdown } from "./useDropdown";

export type AddToListLabels = {
    open_btn: string;
    loading: string;
    load_error: string;
    no_lists: string;
    no_lists_cta: string;
    in_list: string;
    adding: string;
    error: string;
};

// One of the user's lists, as the menu shows it.
type ListChoice = {
    id: number;
    title: string;
    streamers_count: number;
    // Whether the streamer is already in it.
    contains: boolean;
};

function readCookie(name: string): string {
    const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : "";
}

// The user's lists in a menu off a button; picking one adds the streamer to it.
// The lists are fetched each time the menu opens, since another row's menu or
// another tab may have changed them since.
export function AddToList({ profileId, labels }: { profileId: number; labels: AddToListLabels }) {
    const { open, setOpen, rootRef, buttonRef } = useDropdown();
    const menuId = useId();
    const [lists, setLists] = useState<ListChoice[] | null>(null);
    const [loadError, setLoadError] = useState(false);
    const [addingId, setAddingId] = useState<number | null>(null);
    const [error, setError] = useState("");
    // Counts the menu's openings, so a slow answer for an earlier one can't
    // overwrite a newer one.
    const openings = useRef(0);

    async function loadLists() {
        const opening = ++openings.current;
        setLists(null);
        setLoadError(false);
        setError("");
        try {
            const response = await fetch(`/api/lists/?contains=${profileId}`, { credentials: "include" });
            if (!response.ok) {
                throw new Error(`Lists request failed (status ${response.status})`);
            }
            const data: { lists: ListChoice[] } = await response.json();
            if (opening === openings.current) setLists(data.lists);
        } catch {
            if (opening === openings.current) setLoadError(true);
        }
    }

    function toggle() {
        if (!open) loadLists();
        setOpen(!open);
    }

    async function add(listId: number) {
        if (addingId !== null) return;
        setAddingId(listId);
        setError("");
        try {
            const response = await fetch(`/api/lists/${listId}/entries/`, {
                method: "POST",
                credentials: "include",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": readCookie("csrftoken"),
                },
                body: JSON.stringify({ profile_id: profileId }),
            });
            if (response.ok) {
                const saved: { streamers_count: number } = await response.json();
                setLists((prev) => prev && prev.map((one_list) => (
                    one_list.id === listId
                        ? { ...one_list, contains: true, streamers_count: saved.streamers_count }
                        : one_list
                )));
            } else {
                // A 400 says why, e.g. the list is full or the streamer opted out.
                const payload = response.status === 400 ? await response.json() : null;
                setError(messageFrom(payload) ?? labels.error);
            }
        } catch {
            setError(labels.error);
        }
        setAddingId(null);
    }

    return (
        <div ref={rootRef} className="relative">
            <button
                ref={buttonRef}
                type="button"
                onClick={toggle}
                aria-expanded={open}
                aria-controls={menuId}
                className="w-full text-sm p-1 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 border border-blue-600 hover:border-blue-700 cursor-pointer"
            >
                {labels.open_btn} <span aria-hidden="true">▾</span>
            </button>
            {open && (
                <div
                    id={menuId}
                    className="absolute right-0 z-20 mt-1 w-72 max-w-[calc(100vw-3rem)] max-h-80 overflow-y-auto rounded border border-gray-300 bg-white text-sm text-left text-gray-900 shadow-lg"
                >
                    {lists === null && !loadError && <p className="px-3 py-2 text-gray-600">{labels.loading}</p>}
                    {loadError && <p role="alert" className="px-3 py-2 text-red-600">{labels.load_error}</p>}
                    {lists?.length === 0 && (
                        <p className="px-3 py-2">
                            {labels.no_lists}{" "}
                            <Link href="/dashboard" className="text-blue-700 hover:underline">{labels.no_lists_cta}</Link>
                        </p>
                    )}
                    {lists && lists.length > 0 && (
                        <ul className="py-1">
                            {lists.map((one_list) => (
                                <li key={one_list.id}>
                                    <button
                                        type="button"
                                        onClick={() => add(one_list.id)}
                                        disabled={one_list.contains || addingId !== null}
                                        className={`w-full flex flex-row items-baseline justify-between gap-4 px-3 py-2 text-left cursor-pointer hover:bg-gray-100 disabled:cursor-default disabled:hover:bg-white ${one_list.contains ? "text-gray-500" : ""}`}
                                    >
                                        <span className="min-w-0 truncate">{one_list.title}</span>
                                        <span className="shrink-0 text-gray-500">
                                            {one_list.contains
                                                ? `✓ ${labels.in_list}`
                                                : addingId === one_list.id
                                                    ? labels.adding
                                                    : one_list.streamers_count.toLocaleString()}
                                        </span>
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}
                    {error && <p role="alert" className="border-t border-t-gray-200 px-3 py-2 text-red-600">{error}</p>}
                </div>
            )}
        </div>
    );
}
