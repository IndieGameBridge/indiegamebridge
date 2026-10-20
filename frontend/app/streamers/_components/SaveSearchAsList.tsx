"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export type SaveListLabels = {
    open_btn: string;
    title_label: string;
    title_placeholder: string;
    description_label: string;
    description_placeholder: string;
    note: string;
    submit_btn: string;
    saving: string;
    cancel_btn: string;
    error: string;
    title_max_length: number;
    description_max_length: number;
};

function readCookie(name: string): string {
    const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : "";
}

// A 400 from the endpoint carries one user-facing message, keyed by the field it
// is about, or by "detail" for the per-user cap on lists.
function messageFrom(payload: unknown): string | null {
    if (payload && typeof payload === "object") {
        const message = Object.values(payload)[0];
        if (typeof message === "string") return message;
    }
    return null;
}

export function SaveSearchAsList({ search_query, labels }: { search_query: string; labels: SaveListLabels }) {
    const router = useRouter();
    const [open, setOpen] = useState(false);
    const [title, setTitle] = useState("");
    const [description, setDescription] = useState("");
    const [pending, setPending] = useState(false);
    const [error, setError] = useState("");

    async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (pending) return;
        setPending(true);
        setError("");
        try {
            // The search travels as its query string; the backend re-runs it to
            // collect every match, not just the pages loaded here.
            const response = await fetch("/api/lists/", {
                method: "POST",
                credentials: "include",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": readCookie("csrftoken"),
                },
                body: JSON.stringify({ title, description, search: search_query }),
            });
            if (response.ok) {
                // The new list is the dashboard's first card. Stay pending through
                // the navigation so the form can't be sent twice.
                router.push("/dashboard");
                return;
            }
            const payload = response.status === 400 ? await response.json() : null;
            setError(messageFrom(payload) ?? labels.error);
        } catch {
            setError(labels.error);
        }
        setPending(false);
    }

    if (!open) {
        return (
            <button
                type="button"
                onClick={() => setOpen(true)}
                className="text-sm p-1 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 border border-blue-600 hover:border-blue-700 cursor-pointer"
            >
                {labels.open_btn}
            </button>
        );
    }

    return (
        <form
            onSubmit={handleSubmit}
            aria-label={labels.open_btn}
            className="basis-full text-sm grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4 border-t border-t-gray-400 pt-4"
        >
            <div className="flex flex-col gap-1">
                <label htmlFor="save-list-title" className="text-brand-blue">{labels.title_label}</label>
                <input
                    id="save-list-title"
                    type="text"
                    required
                    autoFocus
                    maxLength={labels.title_max_length}
                    placeholder={labels.title_placeholder}
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    className="p-2 border border-gray-300 rounded-sm outline-gray-400"
                />
            </div>
            <div className="flex flex-col gap-1">
                <label htmlFor="save-list-description" className="text-brand-blue">{labels.description_label}</label>
                <textarea
                    id="save-list-description"
                    rows={2}
                    maxLength={labels.description_max_length}
                    placeholder={labels.description_placeholder}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    className="p-2 border border-gray-300 rounded-sm outline-gray-400"
                />
            </div>
            <p className="md:col-span-2 italic">{labels.note}</p>
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
                    onClick={() => { setOpen(false); setError(""); }}
                    disabled={pending}
                    className="text-blue-700 hover:underline cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed"
                >
                    {labels.cancel_btn}
                </button>
            </div>
        </form>
    );
}
