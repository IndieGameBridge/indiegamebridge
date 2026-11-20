"use client";

import { useId, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { BLUE_BUTTON } from "./buttonStyles";

export type StreamerFinderLabels = {
    title: string;
    placeholder: string;
    btn: string;
    hint: string;
    // Shown to a logged-out visitor, after the hint.
    login_note: string;
    // Holds {name}, the streamer's display name.
    opening: string;
    not_found: string;
    invalid: string;
    error: string;
};

type Profile = { login: string; display_name: string };

type Outcome =
    | { kind: "found"; profile: Profile }
    | { kind: "not_found" | "invalid" | "error" };

// What the backend reads at most; a channel link is far shorter.
const MAX_LENGTH = 200;

/**
 * One streamer, looked up by their Twitch login or a link to their channel. A streamer found
 * opens like a shared link to their profile: straight away when signed in, through the login
 * otherwise. The name is checked first, so nobody logs in to find a name we don't have.
 */
export function StreamerFinder({ labels, signedIn }: { labels: StreamerFinderLabels; signedIn: boolean }) {
    const router = useRouter();
    const id = useId();
    const [text, setText] = useState("");
    const [looking, setLooking] = useState(false);
    const [outcome, setOutcome] = useState<Outcome | null>(null);
    const [opening, startTransition] = useTransition();

    async function find() {
        const typed = text.trim();
        if (!typed || looking) return;
        setLooking(true);
        setOutcome(null);
        let found: Outcome;
        try {
            const response = await fetch(`/api/streamers/find/?q=${encodeURIComponent(typed)}`);
            if (!response.ok) throw new Error(`Streamer lookup failed (status ${response.status})`);
            const data: { valid: boolean; profile: Profile | null } = await response.json();
            found = data.profile
                ? { kind: "found", profile: data.profile }
                : { kind: data.valid ? "not_found" : "invalid" };
        } catch {
            found = { kind: "error" };
        }
        setLooking(false);
        setOutcome(found);
        if (found.kind === "found") {
            const login = found.profile.login;
            startTransition(() => router.push(`/streamers/${login}`));
        }
    }

    const message = outcome === null ? null
        : outcome.kind === "found" ? labels.opening.replace("{name}", outcome.profile.display_name)
        : labels[outcome.kind];

    return (
        <form
            role="search"
            className="mt-10"
            onSubmit={(event) => { event.preventDefault(); find(); }}
        >
            <label htmlFor={id} className="block mb-2 font-bold">{labels.title}</label>
            <div className="flex gap-2">
                <input
                    id={id}
                    type="search"
                    // A login or a link, never a word to correct or capitalize.
                    autoComplete="off"
                    autoCapitalize="none"
                    autoCorrect="off"
                    spellCheck={false}
                    enterKeyHint="go"
                    maxLength={MAX_LENGTH}
                    placeholder={labels.placeholder}
                    aria-describedby={`${id}-hint`}
                    // The Games name box's look.
                    className="text-sm px-3 py-2 leading-[normal] border border-gray-300 rounded-sm grow min-w-0 outline-gray-400"
                    value={text}
                    onChange={(event) => { setText(event.target.value); setOutcome(null); }}
                />
                <button
                    type="submit"
                    disabled={looking || opening}
                    className={`${BLUE_BUTTON} shrink-0 cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed`}
                >
                    {labels.btn}
                </button>
            </div>
            <p id={`${id}-hint`} className="mt-2 text-sm text-gray-600">
                {signedIn ? labels.hint : `${labels.hint} ${labels.login_note}`}
            </p>
            <p aria-live="polite" className="text-sm empty:hidden mt-3">{message}</p>
        </form>
    );
}
