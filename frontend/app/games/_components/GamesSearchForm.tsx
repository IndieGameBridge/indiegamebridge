"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import type { GameFilter } from "./types";

export type GamesSearchFormData = {
    aria_label: string;
    filters: GameFilter[];
    btn_text: string;
    search_notes: string[];
};

/**
 * The Games page's filters, for the language page it's on: `path` is that page. Only what
 * differs from a filter's default goes in the address, so a plain page keeps a plain link.
 */
export function GamesSearchForm({ search_form, path, initial_values }: {
    search_form: GamesSearchFormData;
    path: string;
    initial_values: Record<string, string | string[] | undefined>;
}) {
    const router = useRouter();
    const [isPending, startTransition] = useTransition();
    const [values, setValues] = useState<Record<string, string>>(() => {
        const initial: Record<string, string> = {};
        for (const one_filter of search_form.filters) {
            const value = initial_values[one_filter.name];
            if (one_filter.type === "text") {
                initial[one_filter.name] = (Array.isArray(value) ? value[0] : value) ?? "";
                continue;
            }
            const known = one_filter.values.some((option) => String(option.v) === value);
            initial[one_filter.name] = known ? String(value) : String(one_filter.default);
        }
        return initial;
    });

    const submitFilters = () => {
        const params = new URLSearchParams();
        for (const one_filter of search_form.filters) {
            // Typed text goes in with its spaces tidied, so a blank box stays out of the address.
            const value = one_filter.type === "text"
                ? values[one_filter.name].trim().replace(/\s+/g, " ")
                : values[one_filter.name];
            if (value !== String(one_filter.default)) {
                params.set(one_filter.name, value);
            }
        }
        const query = params.toString();
        startTransition(() => {
            router.push(query ? `${path}?${query}` : path, { scroll: false });
        });
    };

    return (
        <div className="bg-white mb-16">
            <form
                className="text-sm grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-5"
                aria-label={search_form.aria_label}
                onSubmit={(event) => { event.preventDefault(); submitFilters(); }}
            >
                {search_form.filters.map((one_filter) => (
                    // The name box takes the rest of the last row on wide screens.
                    <fieldset
                        key={one_filter.name}
                        className={`flex items-center flex-wrap col-span-1 ${one_filter.type === "text" ? "lg:col-span-3" : ""}`}
                    >
                        <legend className="mr-4 text-sm text-brand-blue">{one_filter.label}</legend>
                        {one_filter.type === "text" ? (
                            <input
                                id={one_filter.name}
                                name={one_filter.name}
                                type="search"
                                aria-label={one_filter.label}
                                // A game's name, not something to pick from past searches.
                                autoComplete="off"
                                enterKeyHint="search"
                                maxLength={one_filter.max_length}
                                placeholder={one_filter.placeholder}
                                // The dropdowns' height and text inset: their line height is the font's own,
                                // and their text sits a little in from the padding.
                                className="text-sm px-3 py-2 leading-[normal] border border-gray-300 rounded-sm grow min-w-0 outline-gray-400"
                                value={values[one_filter.name]}
                                onChange={(event) => setValues((previous) => ({ ...previous, [one_filter.name]: event.target.value }))}
                            />
                        ) : (
                            <select
                                id={one_filter.name}
                                name={one_filter.name}
                                aria-label={one_filter.label}
                                className="text-sm p-2 border border-gray-300 rounded-sm grow cursor-pointer outline-gray-400"
                                value={values[one_filter.name]}
                                onChange={(event) => setValues((previous) => ({ ...previous, [one_filter.name]: event.target.value }))}
                            >
                                {one_filter.values.map((option) => (
                                    <option key={String(option.v)} value={option.v}>{option.l}</option>
                                ))}
                            </select>
                        )}
                    </fieldset>
                ))}
                <div className="col-span-1 md:col-span-2 lg:col-span-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-5">
                    <div className="col-span-1 md:col-span-1 lg:col-span-3 text-sm italic">
                        {search_form.search_notes.map((one_note) => (
                            <p key={one_note} className="mb-3 pt-2">{one_note}</p>
                        ))}
                    </div>
                    <fieldset className="flex justify-center col-span-1 items-start">
                        <button
                            type="submit"
                            disabled={isPending}
                            className={isPending
                                ? "text-sm align-baseline bg-gray-300 p-1 rounded-sm text-white hover:bg-gray-300 cursor-not-allowed min-w-36"
                                : "text-sm align-baseline bg-blue-600 p-1 rounded-sm text-white hover:bg-blue-700 cursor-pointer min-w-36"
                            }
                        >
                            {search_form.btn_text}
                        </button>
                    </fieldset>
                </div>
            </form>
        </div>
    );
}
