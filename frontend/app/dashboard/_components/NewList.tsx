"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { ListForm, ListFormLabels } from "../../_components/ListForm";

export type NewListLabels = ListFormLabels & {
    open_btn: string;
};

// Starts an empty list, for adding streamers to one by one. It is sent without a
// search, which is what makes it a list made by hand.
export function NewList({ labels }: { labels: NewListLabels }) {
    const router = useRouter();
    const [open, setOpen] = useState(false);

    if (!open) {
        return (
            <button
                type="button"
                onClick={() => setOpen(true)}
                className="text-sm p-2 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 border border-blue-600 hover:border-blue-700 cursor-pointer"
            >
                {labels.open_btn}
            </button>
        );
    }

    return (
        <ListForm
            id="new-list"
            url="/api/lists/"
            method="POST"
            labels={labels}
            // Straight to the new list, which says where its streamers come from.
            onSaved={(saved) => router.push(`/lists/${saved.id}`)}
            onCancel={() => setOpen(false)}
        />
    );
}
