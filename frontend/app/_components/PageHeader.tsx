"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CurrentUser } from "../_lib/auth";
import { AuthStatus } from "./AuthStatus";

export function NavLink({ href, className, children }: { href: string; className?: string; children: React.ReactNode }) {
    const pathname = usePathname();
    const base = `text-white underline-offset-3 ${className ?? ""}`;
    if (pathname === href) {
        return <span className={`${base} underline`}>{children}</span>;
    }
    return <Link href={href} className={`${base} hover:underline`}>{children}</Link>;
}

export function PageHeader(
    { user, title, description, info, link_to_twitch }: {
        user: CurrentUser | null;
        title?: string;
        description?: string;
        info?: string;
        link_to_twitch?: string;
    }
) {
    return (
        <header className="pb-12 bg-brand-blue text-white shadow-sm shadow-gray-200">
            <section className="border-b border-b-white mb-16 px-6">
                <div className="max-w-[1000] mx-auto">
                    <div className="flex flex-col gap-y-4 md:flex-row lg:flex-row justify-end pb-2 pt-6">
                        <div className="flex flex-col items-center w-full justify-center gap-y-4 gap-x-8 md:mr-auto md:flex-row md:justify-start lg:mr-auto lg:flex-row lg:justify-start">
                            <NavLink href="/">Home</NavLink>
                            <NavLink href="/streamers">Streamers</NavLink>
                        </div>
                        <AuthStatus user={user} />
                    </div>
                </div>
            </section>
            <section className="px-6">
                <div className="max-w-[1000] mx-auto">
                    <div className="flex flex-row items-center justify-between flex-wrap gap-y-8">
                        {title && <h1 className="text-3xl">{title}</h1>}
                        {link_to_twitch
                            && <a className="text-sm align-baseline inline-block py-2 px-4 bg-twitch-brand text-white font-medium rounded hover:bg-twitch-brand-dark text-center border border-twitch-brand hover:border-twitch-brand-dark"
                                href={link_to_twitch} target="_blank" rel="nofollow">Visit Twitch Channel</a>
                        }
                    </div>
                    {description && <p className="mt-6 text-lg">{description}</p>}
                    {info && <p className="mt-6 opacity-70">{info}</p>}
                </div>
            </section>
        </header>
    );
}
