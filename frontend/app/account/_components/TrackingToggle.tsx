"use client";

import { useState } from "react";

function readCookie(name: string): string {
    const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : "";
}

export function TrackingToggle({ initialValue }: { initialValue: boolean }) {
    const [allowed, setAllowed] = useState(initialValue);
    const [pending, setPending] = useState(false);

    async function setValue(next: boolean) {
        if (pending || next === allowed) return;
        setPending(true);
        // Optimistic: flip immediately, roll back if the request fails.
        setAllowed(next);
        const response = await fetch("/auth/settings/", {
            method: "PATCH",
            credentials: "include",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": readCookie("csrftoken"),
            },
            body: JSON.stringify({ allow_tracking: next }),
        });
        if (!response.ok) {
            setAllowed(!next);
        }
        setPending(false);
    }

    return (
        <button
            type="button"
            role="switch"
            aria-checked={allowed}
            onClick={() => setValue(!allowed)}
            disabled={pending}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer ${allowed ? "bg-green-600" : "bg-gray-300"}`}
        >
            <span className="sr-only">Allow feature-usage tracking</span>
            <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${allowed ? "translate-x-6" : "translate-x-1"}`}
            />
        </button>
    );
}
