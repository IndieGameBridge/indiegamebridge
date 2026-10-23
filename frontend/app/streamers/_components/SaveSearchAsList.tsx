"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { ListForm, ListFormLabels } from "../../_components/ListForm";

export type SaveListLabels = ListFormLabels & {
    open_btn: string;
    note: string;
};

export function SaveSearchAsList({ search_query, labels }: { search_query: string; labels: SaveListLabels }) {
    const router = useRouter();
    const [open, setOpen] = useState(false);

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
        <ListForm
            id="save-list"
            url="/api/lists/"
            method="POST"
            // The search travels as its query string; the backend re-runs it to
            // collect every match, not just the pages loaded here.
            extra={{ search: search_query }}
            note={labels.note}
            labels={labels}
            // The new list is the dashboard's first card.
            onSaved={() => router.push("/dashboard")}
            onCancel={() => setOpen(false)}
        />
    );
}
