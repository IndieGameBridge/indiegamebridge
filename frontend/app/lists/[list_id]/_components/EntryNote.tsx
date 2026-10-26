"use client";

import { useState } from "react";

export type EntryNoteLabels = {
    note_label: string;
    add_note: string;
    edit_note: string;
    note_placeholder: string;
    save_note: string;
    saving: string;
    cancel: string;
    note_error: string;
    note_max_length: number;
};

function readCookie(name: string): string {
    const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : "";
}

export function EntryNote({ listId, entryId, initialNote, labels }: {
    listId: number;
    entryId: number;
    initialNote: string;
    labels: EntryNoteLabels;
}) {
    const [note, setNote] = useState(initialNote);
    const [draft, setDraft] = useState(initialNote);
    const [editing, setEditing] = useState(false);
    const [pending, setPending] = useState(false);
    const [error, setError] = useState("");

    function startEditing() {
        setDraft(note);
        setError("");
        setEditing(true);
    }

    async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (pending) return;
        setPending(true);
        setError("");
        try {
            const response = await fetch(`/api/lists/${listId}/entries/${entryId}/`, {
                method: "PATCH",
                credentials: "include",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": readCookie("csrftoken"),
                },
                body: JSON.stringify({ description: draft }),
            });
            if (response.ok) {
                // The backend trims the note, so show what it actually kept.
                const saved: { description: string } = await response.json();
                setNote(saved.description);
                setEditing(false);
            } else {
                // The textarea's maxLength rules out the one 400 the endpoint has,
                // so whatever failed, the draft stays put for another try.
                setError(labels.note_error);
            }
        } catch {
            setError(labels.note_error);
        }
        setPending(false);
    }

    if (!editing) {
        return (
            <div className="border-t border-t-gray-300 pt-4 text-sm">
                {note && (
                    <p className="mb-2 whitespace-pre-line wrap-break-word">
                        <span className="text-brand-blue uppercase">{labels.note_label}: </span>{note}
                    </p>
                )}
                <button type="button" onClick={startEditing} className="text-blue-700 hover:underline cursor-pointer">
                    {note ? labels.edit_note : labels.add_note}
                </button>
            </div>
        );
    }

    return (
        <form onSubmit={handleSubmit} className="border-t border-t-gray-300 pt-4 text-sm flex flex-col gap-2">
            <textarea
                aria-label={labels.note_label}
                autoFocus
                rows={3}
                maxLength={labels.note_max_length}
                placeholder={labels.note_placeholder}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                className="p-2 border border-gray-300 rounded-sm outline-gray-400"
            />
            {error && <p role="alert" className="text-red-600">{error}</p>}
            <div className="flex flex-row items-center gap-6">
                <button
                    type="submit"
                    disabled={pending}
                    className="text-sm p-1 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 border border-blue-600 hover:border-blue-700 cursor-pointer disabled:bg-gray-400 disabled:border-gray-400 disabled:hover:bg-gray-400 disabled:hover:border-gray-400 disabled:cursor-not-allowed"
                >
                    {pending ? labels.saving : labels.save_note}
                </button>
                <button
                    type="button"
                    onClick={() => setEditing(false)}
                    disabled={pending}
                    className="text-blue-700 hover:underline cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed"
                >
                    {labels.cancel}
                </button>
            </div>
        </form>
    );
}
