"use client";

import Link from "next/link";
import { CurrentUser } from "../_lib/auth";
import { AuthStatus } from "./AuthStatus";

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
                        <Link href="/" className="mr-auto text-white hover:underline">Home</Link>
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
