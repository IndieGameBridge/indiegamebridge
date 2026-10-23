"use client";

import { useState } from "react";

export type ListFormLabels = {
    title_label: string;
    title_placeholder: string;
    description_label: string;
    description_placeholder: string;
    submit_btn: string;
    saving: string;
    cancel_btn: string;
    error: string;
    title_max_length: number;
    description_max_length: number;
};

// What the lists endpoints answer a successful save with: enough to open the list.
export type SavedList = { id: number };

function readCookie(name: string): string {
    const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : "";
}

// A 400 from the lists endpoints carries one user-facing message, keyed by the
// field it is about, or by "detail" for the per-user cap on lists.
function messageFrom(payload: unknown): string | null {
    if (payload && typeof payload === "object") {
        const message = Object.values(payload)[0];
        if (typeof message === "string") return message;
    }
    return null;
}

// A list's title and note: for creating a list, from a search or empty, and for
// editing one. The form sends the request itself and leaves what follows, like
// where to go next, to onSaved.
export function ListForm({
    id,
    url,
    method,
    extra,
    initialTitle = "",
    initialDescription = "",
    note,
    labels,
    onSaved,
    onCancel,
}: {
    // Prefixes the inputs' ids, which have to be unique on the page.
    id: string;
    url: string;
    method: "POST" | "PATCH";
    // Sent along with the title and note, e.g. the search to save.
    extra?: Record<string, unknown>;
    initialTitle?: string;
    initialDescription?: string;
    // Shown above the buttons, to say what saving will do.
    note?: string;
    labels: ListFormLabels;
    // The form stays disabled from here on, so it can't be sent twice while a
    // navigation runs.
    onSaved: (saved: SavedList) => void;
    onCancel: () => void;
}) {
    const [title, setTitle] = useState(initialTitle);
    const [description, setDescription] = useState(initialDescription);
    const [pending, setPending] = useState(false);
    const [error, setError] = useState("");

    async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (pending) return;
        setPending(true);
        setError("");
        try {
            const response = await fetch(url, {
                method,
                credentials: "include",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": readCookie("csrftoken"),
                },
                body: JSON.stringify({ ...extra, title, description }),
            });
            if (response.ok) {
                onSaved(await response.json());
                return;
            }
            const payload = response.status === 400 ? await response.json() : null;
            setError(messageFrom(payload) ?? labels.error);
        } catch {
            setError(labels.error);
        }
        setPending(false);
    }

    return (
        <form
            onSubmit={handleSubmit}
            aria-label={labels.submit_btn}
            className="basis-full text-sm grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4 border-t border-t-gray-400 pt-4"
        >
            <div className="flex flex-col gap-1">
                <label htmlFor={`${id}-title`} className="text-brand-blue">{labels.title_label}</label>
                <input
                    id={`${id}-title`}
                    type="text"
                    required
                    autoFocus
                    // A new list's title, not something to pick from past ones.
                    autoComplete="off"
                    maxLength={labels.title_max_length}
                    placeholder={labels.title_placeholder}
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    className="p-2 border border-gray-300 rounded-sm outline-gray-400"
                />
            </div>
            <div className="flex flex-col gap-1">
                <label htmlFor={`${id}-description`} className="text-brand-blue">{labels.description_label}</label>
                <textarea
                    id={`${id}-description`}
                    rows={2}
                    autoComplete="off"
                    maxLength={labels.description_max_length}
                    placeholder={labels.description_placeholder}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    className="p-2 border border-gray-300 rounded-sm outline-gray-400"
                />
            </div>
            {note && <p className="md:col-span-2 italic">{note}</p>}
            {error && <p role="alert" className="md:col-span-2 text-red-600">{error}</p>}
            <div className="md:col-span-2 flex flex-row items-center gap-6">
                <button
                    type="submit"
                    disabled={pending}
                    className="text-sm p-2 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 border border-blue-600 hover:border-blue-700 cursor-pointer disabled:bg-gray-400 disabled:border-gray-400 disabled:hover:bg-gray-400 disabled:hover:border-gray-400 disabled:cursor-not-allowed"
                >
                    {pending ? labels.saving : labels.submit_btn}
                </button>
                <button
                    type="button"
                    onClick={onCancel}
                    disabled={pending}
                    className="text-blue-700 hover:underline cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed"
                >
                    {labels.cancel_btn}
                </button>
            </div>
        </form>
    );
}
