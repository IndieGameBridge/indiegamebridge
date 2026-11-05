"use client";

import { useId } from "react";
import { ProgressLink as Link } from "./ProgressLink";
import { useRouter, usePathname } from "next/navigation";
import { Fragment } from "react/jsx-runtime";
import { NavLink } from "./PageHeader";
import { useDropdown } from "./useDropdown";

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

// Settings and Log out in a menu off the user icon, which leaves the top bar's
// row for the pages people go to more often.
function UserMenu() {
    const router = useRouter();
    const pathname = usePathname();
    const { open, setOpen, rootRef, buttonRef } = useDropdown();
    const menuId = useId();

    async function handleLogout() {
        setOpen(false);
        await fetch("/auth/logout/", {
            method: "POST",
            credentials: "include",
            headers: { "X-CSRFToken": readCookie("csrftoken") },
        });
        router.refresh();
    }

    return (
        <div ref={rootRef} className="relative">
            <button
                ref={buttonRef}
                type="button"
                onClick={() => setOpen(!open)}
                aria-label="Account menu"
                aria-expanded={open}
                aria-controls={menuId}
                className="flex items-center gap-x-1 -m-1 p-1 rounded text-white cursor-pointer hover:bg-white/15 aria-expanded:bg-white/15"
            >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" aria-hidden="true" className="w-6 h-6">
                    <circle cx="12" cy="12" r="10" />
                    <circle cx="12" cy="10" r="3" />
                    <path d="M6.2 19a6.5 6.5 0 0 1 11.6 0" />
                </svg>
                <span aria-hidden="true">▾</span>
            </button>
            {open && (
                <div
                    id={menuId}
                    className="absolute left-0 md:left-auto md:right-0 z-20 mt-2 w-40 rounded border border-gray-300 bg-white text-sm text-left text-gray-900 shadow-lg"
                >
                    <ul className="py-1">
                        <li>
                            <Link
                                href="/account"
                                onClick={() => setOpen(false)}
                                aria-current={pathname === "/account" ? "page" : undefined}
                                className="block px-3 py-2 hover:bg-gray-100 aria-[current=page]:font-medium"
                            >
                                Settings
                            </Link>
                        </li>
                        <li>
                            <button type="button" onClick={handleLogout} className="w-full px-3 py-2 text-left cursor-pointer hover:bg-gray-100">Log out</button>
                        </li>
                    </ul>
                </div>
            )}
        </div>
    );
}

export function AuthStatus({ user }: AuthStatusProps) {
    const pathname = usePathname();

    return (
        <div className="flex gap-x-8 gap-y-4 flex-col justify-center items-start md:flex-row md:items-end lg:flex-row lg:items-end">
            {!user
                ? (pathname === "/login"
                    ? <span className="text-white underline underline-offset-3 text-nowrap">Log in</span>
                    : <a href="/login" className="cursor-pointer text-white hover:underline underline-offset-3 text-nowrap">Log in</a>)
                : <Fragment>
                        <NavLink href="/dashboard">Dashboard</NavLink>
                        <UserMenu />
                    </Fragment>
            }
        </div>
    );
}
