"use client";

import { useState } from "react";
import { Fragment } from "react/jsx-runtime";
import { useRouter } from "next/navigation";

function readCookie(name: string): string {
    const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : "";
}

export function OptOutButton({ label, pendingLabel }: { label: string; pendingLabel: string }) {
    const router = useRouter();
    const [pending, setPending] = useState(false);

    async function handleOptOut() {
        setPending(true);
        await fetch("/auth/optout/", {
            method: "POST",
            credentials: "include",
            headers: { "X-CSRFToken": readCookie("csrftoken") },
        });
        router.replace("/optout?status=done");
    }

    return (
        <Fragment>
            <button
                type="button"
                onClick={handleOptOut}
                disabled={pending}
                className="text-sm items-center justify-center gap-3 px-8 py-2 bg-red-600 text-white font-medium rounded hover:bg-red-700 border border-red-600 hover:border-red-700 disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer"
            >
                {label}
            </button>
            {pending && (
                <p role="status" aria-live="polite" className="text-sm text-gray-600 mt-4">
                    {pendingLabel}
                </p>
            )}
        </Fragment>
    );
}
