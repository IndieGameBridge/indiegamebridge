"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { ExportMenu, ExportMenuLabels } from "../../../_components/ExportMenu";
import { ListForm, ListFormLabels } from "../../../_components/ListForm";

export type ListActionsLabels = {
    edit_btn: string;
    delete_btn: string;
    delete_confirm: string;
    delete_error: string;
    form: ListFormLabels;
    // Absent until the page's cached text is rebuilt with it.
    export?: ExportMenuLabels;
};

function readCookie(name: string): string {
    const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : "";
}

// Export the list, edit its title and note, or delete it. An empty list has
// nothing to export.
export function ListActions({ list, exportable, labels }: {
    list: { id: number; title: string; description: string };
    exportable: boolean;
    labels: ListActionsLabels;
}) {
    const router = useRouter();
    const [editing, setEditing] = useState(false);
    const [deleting, setDeleting] = useState(false);
    const [error, setError] = useState("");

    async function handleDelete() {
        if (deleting || !window.confirm(labels.delete_confirm)) return;
        setDeleting(true);
        setError("");
        let deleted = false;
        try {
            const response = await fetch(`/api/lists/${list.id}/`, {
                method: "DELETE",
                credentials: "include",
                headers: { "X-CSRFToken": readCookie("csrftoken") },
            });
            deleted = response.ok;
        } catch {
            deleted = false;
        }
        if (deleted) {
            // Stay disabled through the navigation, so it can't be sent twice.
            router.push("/dashboard");
            return;
        }
        setError(labels.delete_error);
        setDeleting(false);
    }

    if (editing) {
        return (
            <ListForm
                id="edit-list"
                url={`/api/lists/${list.id}/`}
                method="PATCH"
                initialTitle={list.title}
                initialDescription={list.description}
                labels={labels.form}
                // The title and note show in the page header, so render the page
                // again around them.
                onSaved={() => {
                    setEditing(false);
                    router.refresh();
                }}
                onCancel={() => setEditing(false)}
            />
        );
    }

    return (
        <div className="flex flex-col items-end gap-2">
            <div className="flex flex-row items-center gap-6">
                {exportable && labels.export && (
                    <ExportMenu url={`/api/lists/${list.id}/export/`} labels={labels.export} />
                )}
                <button
                    type="button"
                    onClick={() => setEditing(true)}
                    disabled={deleting}
                    className="text-sm p-1 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 border border-blue-600 hover:border-blue-700 cursor-pointer disabled:bg-gray-400 disabled:border-gray-400 disabled:hover:bg-gray-400 disabled:hover:border-gray-400 disabled:cursor-not-allowed"
                >
                    {labels.edit_btn}
                </button>
                <button
                    type="button"
                    onClick={handleDelete}
                    disabled={deleting}
                    className="text-sm p-1 bg-red-600 text-white font-medium rounded hover:bg-red-700 min-w-36 border border-red-600 hover:border-red-700 cursor-pointer disabled:bg-gray-400 disabled:border-gray-400 disabled:hover:bg-gray-400 disabled:hover:border-gray-400 disabled:cursor-not-allowed"
                >
                    {labels.delete_btn}
                </button>
            </div>
            {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
        </div>
    );
}
