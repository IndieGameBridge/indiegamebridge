"use client";

import { useState } from "react";
import { Fragment } from "react/jsx-runtime";

const VARIANT_CLASSES = {
    twitch: {
        idle: "bg-twitch-brand border-twitch-brand hover:bg-twitch-brand-dark hover:border-twitch-brand-dark",
        pending: "bg-twitch-brand border-twitch-brand opacity-60 cursor-not-allowed pointer-events-none",
    },
    danger: {
        idle: "bg-red-600 border-red-600 hover:bg-red-700 hover:border-red-700",
        pending: "bg-red-600 border-red-600 opacity-60 cursor-not-allowed pointer-events-none",
    },
} as const;

export function TwitchLoginButton({
    href,
    label,
    pendingLabel,
    variant = "twitch",
}: {
    href: string;
    label: string;
    pendingLabel: string;
    variant?: keyof typeof VARIANT_CLASSES;
}) {
    const [pending, setPending] = useState(false);

    function handleClick(event: React.MouseEvent<HTMLAnchorElement>) {
        event.preventDefault();
        if (pending) return;
        setPending(true);
        // Defer the full-page navigation one tick so React paints the disabled
        // state and message first — otherwise the redirect can begin before the
        // user sees any feedback.
        setTimeout(() => { window.location.href = href; }, 0);
    }

    return (
        <Fragment>
            <a
                href={href}
                onClick={handleClick}
                aria-disabled={pending}
                className={`text-sm inline-flex items-center justify-center gap-3 px-8 py-2 text-white font-medium rounded border ${
                    pending ? VARIANT_CLASSES[variant].pending : VARIANT_CLASSES[variant].idle
                }`}
            >
                <svg aria-hidden="true" viewBox="0 0 24 24" className="w-5 h-5 fill-current">
                    <path d="M4.265 0L1 3.265v17.47h5.47V24h3.265l3.265-3.265h5.47L24 14.47V0H4.265zm17.47 13.265L18.47 16.53h-5.47l-3.265 3.265V16.53H5.47V2.265h16.265v11zm-5.47-6.53h-2.265v6.53h2.265v-6.53zm-5.47 0H8.53v6.53h2.265v-6.53z" />
                </svg>
                <span>{label}</span>
            </a>
            {pending && (
                <p role="status" aria-live="polite" className="text-sm text-gray-600 mt-4 text-center">
                    {pendingLabel}
                </p>
            )}
        </Fragment>
    );
}
