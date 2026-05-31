"use client";

import { useState } from "react";

function readCookie(name: string): string {
    const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : "";
}

// `initialExcluded` is the opt-out state from the backend (true = excluded).
// The switch itself reads positively: ON = streams tracking allowed = NOT excluded.
export function ExclusionToggle({ initialExcluded, confirmText }: { initialExcluded: boolean; confirmText: string }) {
    const [allowed, setAllowed] = useState(!initialExcluded);
    const [pending, setPending] = useState(false);

    async function setAllow(next: boolean) {
        if (pending || next === allowed) return;
        // Confirm only when opting out (turning tracking off); opting back in needs no warning.
        if (!next && !window.confirm(confirmText)) {
            return;
        }
        setPending(true);
        // Optimistic: flip immediately, roll back if the request fails.
        setAllowed(next);
        const response = await fetch("/auth/stream-exclusion/", {
            method: "PATCH",
            credentials: "include",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": readCookie("csrftoken"),
            },
            body: JSON.stringify({ excluded: !next }),
        });
        if (!response.ok) {
            setAllowed(!next);
        } else {
            const data: { excluded: boolean } = await response.json();
            setAllowed(!data.excluded);
        }
        setPending(false);
    }

    return (
        <button
            type="button"
            role="switch"
            aria-checked={allowed}
            onClick={() => setAllow(!allowed)}
            disabled={pending}
            className={`relative inline-flex h-6 w-11 min-w-11 items-center rounded-full transition-colors disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer ${allowed ? "bg-green-600" : "bg-gray-300"}`}
        >
            <span className="sr-only">Allow streams tracking for my Twitch ID</span>
            <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${allowed ? "translate-x-6" : "translate-x-1"}`}
            />
        </button>
    );
}
