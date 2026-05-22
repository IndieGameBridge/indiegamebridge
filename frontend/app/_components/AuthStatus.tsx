"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Fragment } from "react/jsx-runtime";

export type AuthStatusProps = {
    user: {
        twitch_id: number;
        username: string;
        display_name: string;
        email: string;
    } | null;
};

function readCookie(name: string): string {
    const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : "";
}

export function AuthStatus({ user }: AuthStatusProps) {
    const router = useRouter();

    async function handleLogout() {
        await fetch("/auth/logout/", {
            method: "POST",
            credentials: "include",
            headers: { "X-CSRFToken": readCookie("csrftoken") },
        });
        router.refresh();
    }

    return (
        <div className="flex gap-x-8 gap-y-2 flex-col md:flex-row lg:flex-row items-end">
            {!user
                ? <a href="/login" className="cursor-pointer text-white hover:underline underline-offset-3">Log in</a>
                : <Fragment>
                        <span className="text-white">Hi, <Link className="text-white cursor-pointer hover:underline underline-offset-3" href="/account">{user.display_name}</Link></span>
                        <button type="button" onClick={handleLogout} className="text-white cursor-pointer hover:underline underline-offset-3">Log out</button>
                    </Fragment>
            }
        </div>
    );
}
