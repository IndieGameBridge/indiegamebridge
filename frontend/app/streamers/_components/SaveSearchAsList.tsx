"use client";

import { useId, useState } from "react";
import { useRouter } from "next/navigation";

import { ListForm, ListFormLabels } from "../../_components/ListForm";
import { useDropdown } from "../../_components/useDropdown";
import { AddSearchToList, AddSearchToListLabels } from "./AddSearchToList";

export type SaveListLabels = {
    open_btn: string;
    new_list_btn: string;
    existing_list_btn: string;
    new_list: ListFormLabels & { note: string };
    existing_list: AddSearchToListLabels;
};

// A menu beside the result count: save every streamer the search found as a
// new list, or add them to one of the user's lists.
export function SaveSearchAsList({ search_query, labels }: { search_query: string; labels: SaveListLabels }) {
    const router = useRouter();
    const { open, setOpen, rootRef, buttonRef } = useDropdown();
    const menuId = useId();
    const [form, setForm] = useState<"new" | "existing" | null>(null);

    function choose(choice: "new" | "existing") {
        setOpen(false);
        setForm(choice);
    }

    if (form === "new") {
        return (
            <ListForm
                id="save-list"
                url="/api/lists/"
                method="POST"
                // The search travels as its query string; the backend re-runs it to
                // collect every match, not just the pages loaded here.
                extra={{ search: search_query }}
                note={labels.new_list.note}
                labels={labels.new_list}
                // The new list is the dashboard's first card.
                onSaved={() => router.push("/dashboard")}
                onCancel={() => setForm(null)}
            />
        );
    }

    if (form === "existing") {
        return <AddSearchToList search_query={search_query} labels={labels.existing_list} onClose={() => setForm(null)} />;
    }

    const choiceClassName = "w-full px-3 py-2 text-left cursor-pointer hover:bg-gray-100";
    return (
        <div ref={rootRef} className="relative">
            <button
                ref={buttonRef}
                type="button"
                onClick={() => setOpen(!open)}
                aria-expanded={open}
                aria-controls={menuId}
                className="w-full text-sm p-1 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 border border-blue-600 hover:border-blue-700 cursor-pointer"
            >
                {labels.open_btn} <span aria-hidden="true">▾</span>
            </button>
            {open && (
                <ul
                    id={menuId}
                    className="absolute right-0 z-20 mt-1 w-56 rounded border border-gray-300 bg-white py-1 text-sm text-left text-gray-900 shadow-lg"
                >
                    <li>
                        <button type="button" onClick={() => choose("new")} className={choiceClassName}>
                            {labels.new_list_btn}
                        </button>
                    </li>
                    <li>
                        <button type="button" onClick={() => choose("existing")} className={choiceClassName}>
                            {labels.existing_list_btn}
                        </button>
                    </li>
                </ul>
            )}
        </div>
    );
}
