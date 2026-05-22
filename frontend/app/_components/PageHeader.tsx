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
    { user, title, description, info }: {
        user: CurrentUser | null;
        title?: string;
        description?: string;
        info?: string;
    }
) {
    return (
        <header className="pb-12 bg-brand-blue text-white shadow-sm shadow-gray-200">
            <section className="border-b border-b-white mb-16 px-6">
                <div className="max-w-[1000] mx-auto">
                    <div className="flex justify-end pb-2 pt-6">
                        <div className="mr-auto">
                            <NavLink href="/" className="pr-6">Home</NavLink>
                            <NavLink href="/streamers">Streamers</NavLink>
                        </div>
                        <AuthStatus user={user} />
                    </div>
                </div>
            </section>
            <section className="px-6">
                <div className="max-w-[1000] mx-auto">
                    {title && <h1 className="text-3xl font-bold">{title}</h1>}
                    {description && <p className="mt-6 text-lg">{description}</p>}
                    {info && <p className="mt-6 text-sm opacity-70">{info}</p>}
                </div>
            </section>
        </header>
    );
}
