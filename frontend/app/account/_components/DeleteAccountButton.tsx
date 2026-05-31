"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

function readCookie(name: string): string {
    const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : "";
}

export function DeleteAccountButton({ optOutLabel, confirmText, buttonLabel }: { optOutLabel: string; confirmText: string; buttonLabel: string }) {
    const router = useRouter();
    const [alsoOptOut, setAlsoOptOut] = useState(false);
    const [pending, setPending] = useState(false);

    async function handleDelete() {
        if (!window.confirm(confirmText)) {
            return;
        }
        setPending(true);
        const response = await fetch("/auth/account/", {
            method: "DELETE",
            credentials: "include",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": readCookie("csrftoken"),
            },
            body: JSON.stringify({ opt_out: alsoOptOut }),
        });
        if (response.ok) {
            // Account is gone; land on the (logged-out) home page.
            router.replace("/");
            router.refresh();
        } else {
            setPending(false);
        }
    }

    return (
        <div>
            <label className="flex items-center gap-2 text-sm text-gray-700 mb-8">
                <input
                    type="checkbox"
                    checked={alsoOptOut}
                    onChange={(e) => setAlsoOptOut(e.target.checked)}
                    className="text-sm w-4 h-4 rounded mr-2 cursor-pointer"
                />
                {optOutLabel}
            </label>
            <button
                type="button"
                onClick={handleDelete}
                disabled={pending}
                className="text-sm px-8 py-2 bg-red-600 text-white font-medium rounded hover:bg-red-700 border border-red-600 hover:border-red-700 disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer"
            >
                {buttonLabel}
            </button>
        </div>
    );
}
