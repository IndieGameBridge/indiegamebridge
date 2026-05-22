"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Fragment, useState } from "react";
import { CurrentUser } from "../_lib/auth";

export type FieldData = {
    v: string | number;
    l: string;
};

export type SearchStreamerFilterData = {
    ui_control: string;
    name: string;
    label: string;
    values: FieldData[];
    default: (string | number)[] | string | number;
    min_values: FieldData[];
    min_default: string | number;
    max_values: FieldData[];
    max_default: string | number;
};

export type SearchFormData = {
    title: string;
    aria_label: string;
    filters: SearchStreamerFilterData[];
    btn_text: string;
    demo_title: string;
    demo_note: string;
    search_notes: string[];
    cta_link_text: string;
};

export type SearchFormInitialValues = Record<string, string | string[] | undefined>;

function toArray(value: string | string[] | undefined): string[] | undefined {
    if (value === undefined) return undefined;
    return Array.isArray(value) ? value : [value];
}

function toString(value: string | string[] | undefined): string | undefined {
    if (value === undefined) return undefined;
    return Array.isArray(value) ? value[0] : value;
}

// URL params are always strings, but filter values may be typed (e.g. wdays
// uses numbers). Resolve a raw string against the configured allowed values
// and return the typed counterpart so equality checks (`.includes`, `!==`)
// work in checkbox state and toggle handlers.
function coerceToAllowed(raw: string, allowed: (string | number)[]): string | number {
    if (allowed.includes(raw)) return raw;
    for (const one_allowed of allowed) {
        if (String(one_allowed) === raw) return one_allowed;
    }
    return raw;
}

export function SearchStreamerForm({
    search_form,
    user,
    initial_values,
}: {
    search_form: SearchFormData;
    user: CurrentUser | null;
    initial_values?: SearchFormInitialValues;
}) {
    const router = useRouter();

    const [formData, setFormData] = useState<Record<string, any>>(() => {
        const initial: Record<string, any> = {};
        const overrides = initial_values ?? {};
        for (const one_filter of search_form.filters) {
            if (one_filter.ui_control === 'multiselect') {
                const default_array = Array.isArray(one_filter.default) ? one_filter.default : [one_filter.default];
                const allowed = one_filter.values.map((one_value) => one_value.v);
                const override_arr = toArray(overrides[one_filter.name]);
                initial[one_filter.name] = override_arr
                    ? override_arr.map((raw) => coerceToAllowed(raw, allowed))
                    : [...default_array];
            } else if (one_filter.ui_control === 'range') {
                const min_key = `${one_filter.name}min`;
                const max_key = `${one_filter.name}max`;
                initial[min_key] = toString(overrides[min_key]) ?? one_filter.min_default;
                initial[max_key] = toString(overrides[max_key]) ?? one_filter.max_default;
            } else if (one_filter.ui_control === 'dropdown') {
                initial[one_filter.name] =
                    toString(overrides[one_filter.name]) ?? one_filter.default;
            }
        }
        return initial;
    });

    const handleCheckboxChange = (filterName: string, value: string | number, isChecked: boolean) => {
    setFormData((prev) => {
        const currentValues = prev[filterName] || [];
            if (isChecked) {
                return { ...prev, [filterName]: [...currentValues, value] };
            } else {
                return { ...prev, [filterName]: currentValues.filter((v: string) => v !== value) };
            }
        });
    };

    const handleSelectRange = (filterName: string, type: 'min' | 'max', value: string) => {
        setFormData((prev) => ({
            ...prev,
            [`${filterName + type}`]: value
        }));
    };

    const handleDropdownChange = (filterName: string, value: string) => {
        setFormData((prev) => ({
            ...prev,
            [filterName]: value
        }));
    };

    const submitFilters = () => {
        if (!user) return;

        const params = new URLSearchParams();
        for (const one_filter of search_form.filters) {
            if (one_filter.ui_control === 'multiselect') {
                const values = (formData[one_filter.name] ?? []) as string[];
                for (const v of values) params.append(one_filter.name, v);
            } else if (one_filter.ui_control === 'range') {
                const min_key = `${one_filter.name}min`;
                const max_key = `${one_filter.name}max`;
                if (formData[min_key] !== undefined && formData[min_key] !== "") {
                    params.append(min_key, formData[min_key]);
                }
                if (formData[max_key] !== undefined && formData[max_key] !== "") {
                    params.append(max_key, formData[max_key]);
                }
            } else if (one_filter.ui_control === 'dropdown') {
                if (formData[one_filter.name] !== undefined && formData[one_filter.name] !== "") {
                    params.append(one_filter.name, formData[one_filter.name]);
                }
            }
        }

        router.push(`/streamers?${params.toString()}`);
    };

    return (
        <div className="overflow-hidden rounded-sm border border-gray-200 shadow-sm shadow-gray-200 bg-white p-6">
            <div className="uppercase mb-5 text-brand-blue text-lg">{search_form.title}</div>
            <form className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-5" aria-label={search_form.aria_label} onSubmit={(event) => { event.preventDefault(); submitFilters(); }}>
                {search_form.filters.map((one_filter, index) => (
                    <fieldset key={one_filter.name}
                            className={`flex items-center flex-wrap col-span-1 ${
                                one_filter.ui_control === 'multiselect'
                                    ? one_filter.values.length > 10
                                        ? 'lg:col-span-3 md:col-span-2 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-1'
                                        : (one_filter.values.length > 3
                                            ? 'lg:col-span-2 md:col-span-2'
                                            : ''
                                        )
                                    : ''
                                }`}>
                        <legend className="mr-4 text-sm text-brand-blue">{one_filter.label}</legend>
                        {(() => {
                            switch (one_filter.ui_control) {

                                case 'multiselect':
                                    return (
                                        <Fragment>
                                            {one_filter.values.map((one_value, index) => {
                                                const id = `${one_filter.name}_${index}`;
                                                const isChecked = formData[one_filter.name]?.includes(one_value.v) || false;

                                                return (
                                                    <div key={id} className="mr-5 mb-1 flex-row flex items-center">
                                                        <input id={id}
                                                            type="checkbox"
                                                            name={one_filter.name}
                                                            value={one_value.v}
                                                            className="w-4 h-4 rounded mr-2 cursor-pointer"
                                                            checked={isChecked}
                                                            onChange={(e) => handleCheckboxChange(one_filter.name, one_value.v, e.target.checked)}
                                                        />
                                                        <label htmlFor={id} className="cursor-pointer">{one_value.l}</label>
                                                    </div>
                                                );
                                            })}
                                        </Fragment>
                                    );

                                case 'range':
                                    return (
                                        <Fragment>
                                            <select id={`${one_filter.name}min`}
                                                name={`${one_filter.name}min`}
                                                className="p-2 border border-gray-200 rounded-sm grow cursor-pointer outline-gray-400"
                                                value={formData[`${one_filter.name}min`] || one_filter.min_default || ''}
                                                onChange={(e) => handleSelectRange(one_filter.name, 'min', e.target.value)}
                                            >
                                                {one_filter.min_values.map((one_value, index) => (
                                                    <option key={`${one_filter.name}min_${index}`} value={one_value.v}>
                                                        {one_value.l}
                                                    </option>
                                                ))}
                                            </select>
                                            <span className="p-2">to</span>
                                            <select id={`${one_filter.name}max`}
                                                name={`${one_filter.name}max`}
                                                className="p-2 border border-gray-200 rounded-sm grow cursor-pointer outline-gray-400"
                                                value={formData[`${one_filter.name}max`] || one_filter.max_default || ''}
                                                onChange={(e) => handleSelectRange(one_filter.name, 'max', e.target.value)}
                                            >
                                                {one_filter.max_values.map((one_value, index) => (
                                                    <option key={`${one_filter.name}max_${index}`} value={one_value.v}>
                                                        {one_value.l}
                                                    </option>
                                                ))}
                                            </select>
                                        </Fragment>
                                    );

                                case 'dropdown':
                                    return (
                                        <Fragment>
                                            <select id={one_filter.name}
                                                name={one_filter.name}
                                                className="p-2 border border-gray-200 rounded-sm grow cursor-pointer outline-gray-400"
                                                value={formData[one_filter.name] || one_filter.default || ''}
                                                onChange={(e) => handleDropdownChange(one_filter.name, e.target.value)}
                                            >
                                                {one_filter.values.map((one_value, index) => (
                                                    <option key={`${one_filter.name}_${index}`} value={one_value.v}>
                                                        {one_value.l}
                                                    </option>
                                                ))}
                                            </select>
                                        </Fragment>
                                    );

                                default:
                                    return null;
                            }
                        })()}
                    </fieldset>
                ))}
                <div className="col-span-1 md:col-span-2 lg:col-span-3 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-5">
                    <div className="col-span-1 md:col-span-1 lg:col-span-2 text-sm italic">
                        {search_form.search_notes.map((one_note, index) => (
                            <div key={`note-${index}`} className="before:content-(--note-marker) ml-4 before:absolute before:-left-4 relative"
                                style={{ ["--note-marker" as any]: `"${"*".repeat(index + 1)}"` }}
                            >{one_note}</div>
                        ))}
                    </div>
                    <fieldset className="flex justify-center col-span-1 items-start">
                        <button type="submit" disabled={!user}
                            className={!user
                                ? "bg-gray-300 px-8 py-2 rounded-sm text-white hover:bg-gray-300 cursor-not-allowed shadow-sm shadow-gray-200 min-w-40"
                                : "bg-blue-600 px-8 py-2 rounded-sm text-white hover:bg-blue-700 cursor-pointer shadow-sm shadow-gray-200 min-w-40"
                            }
                        >{search_form.btn_text}</button>
                    </fieldset>
                </div>
                {!user
                    ? <div className="col-span-1 lg:col-span-3 md:col-span-2 text-orange-600 mt-4 border-t border-orange-500 pt-4">
                        <div>
                            <span className="font-bold uppercase">{search_form.demo_title}</span>
                            <span> {search_form.demo_note}</span>
                        </div>
                        <div className="text-center mt-4">
                            <Link href="/login" className="underline text-blue-700 hover:text-blue-500 ml-2">{search_form.cta_link_text}</Link>
                        </div>
                    </div>
                    : null
                }
            </form>
        </div>
    );
};
