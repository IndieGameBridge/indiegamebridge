"use client";

import { useId, useState } from "react";

import { useDropdown } from "./useDropdown";

export type ExportMenuLabels = {
    open_btn: string;
    // The formats to offer, in order.
    choices: { file_format: string; label: string }[];
    exporting: string;
    error: string;
    throttled: string;
};

// The download's name as the backend gave it: filename*= when the name has
// non-ASCII characters in it, filename= otherwise.
function filenameFrom(header: string | null, fallback: string): string {
    const encoded = header?.match(/filename\*=utf-8''([^;]+)/i);
    if (encoded) return decodeURIComponent(encoded[1]);
    const plain = header?.match(/filename="((?:[^"\\]|\\.)*)"/);
    return plain ? plain[1].replace(/\\(.)/g, "$1") : fallback;
}

// The formats in a menu off a button; picking one downloads the list or search
// as a file. `url` is the export endpoint up to the format, and `query` the
// search's query string, if it's a search. The file is fetched rather than
// linked to, so a refusal - the hourly export limit, say - shows here as a
// message instead of a page of JSON.
export function ExportMenu({ url, query = "", labels }: { url: string; query?: string; labels: ExportMenuLabels }) {
    const { open, setOpen, rootRef, buttonRef } = useDropdown();
    const menuId = useId();
    const [exporting, setExporting] = useState<string | null>(null);
    const [error, setError] = useState("");

    function toggle() {
        if (!open) setError("");
        setOpen(!open);
    }

    async function download(fileFormat: string) {
        if (exporting !== null) return;
        setExporting(fileFormat);
        setError("");
        try {
            const response = await fetch(`${url}${fileFormat}/${query ? `?${query}` : ""}`, { credentials: "include" });
            if (response.ok) {
                const link = document.createElement("a");
                link.href = URL.createObjectURL(await response.blob());
                link.download = filenameFrom(response.headers.get("Content-Disposition"), `indiegamebridge.${fileFormat}`);
                document.body.appendChild(link);
                link.click();
                link.remove();
                // Some browsers read the file after click() returns, so the URL
                // has to outlive this handler.
                setTimeout(() => URL.revokeObjectURL(link.href), 60_000);
                setOpen(false);
            } else if (response.status === 429) {
                const seconds = Number(response.headers.get("Retry-After")) || 60;
                setError(labels.throttled.replace("{minutes}", String(Math.ceil(seconds / 60))));
            } else {
                setError(labels.error);
            }
        } catch {
            setError(labels.error);
        }
        setExporting(null);
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
                    className="absolute right-0 z-20 mt-1 w-56 max-w-[calc(100vw-3rem)] rounded border border-gray-300 bg-white text-sm text-left text-gray-900 shadow-lg"
                >
                    <ul className="py-1">
                        {labels.choices.map((choice) => (
                            <li key={choice.file_format}>
                                <button
                                    type="button"
                                    onClick={() => download(choice.file_format)}
                                    disabled={exporting !== null}
                                    className="w-full flex flex-row items-baseline justify-between gap-4 px-3 py-2 text-left cursor-pointer hover:bg-gray-100 disabled:cursor-default disabled:hover:bg-white"
                                >
                                    <span>{choice.label}</span>
                                    {exporting === choice.file_format && (
                                        <span className="shrink-0 text-gray-500">{labels.exporting}</span>
                                    )}
                                </button>
                            </li>
                        ))}
                    </ul>
                    {error && <p role="alert" className="border-t border-t-gray-200 px-3 py-2 text-red-600">{error}</p>}
                </div>
            )}
        </div>
    );
}
