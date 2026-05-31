import type { Metadata } from "next";
import Link from "next/link";

import { serverFetch } from "../_lib/server-fetch";

export const metadata: Metadata = {
    title: "Privacy Policy — IndieGameBridge",
    // A privacy policy is a public legal page, so unlike the other secondary
    // pages it's left indexable/followable.
    robots: { index: true, follow: true },
};

export type PrivacyPolicyPageContent = {
    title: string;
    return_home: string;
    last_updated: string;
    intro: string;
    sections: { heading: string; body: string }[];
};

export default async function PrivacyPolicyPage() {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const response = await serverFetch(`${apiBase}/pages/privacy/`);

    if (!response.ok) {
        throw new Error(`Failed to load privacy policy page content (status ${response.status})`);
    }

    const content: PrivacyPolicyPageContent = await response.json();

    return (
        <main className="flex-1 px-6">
            <div className="max-w-2xl mx-auto py-24">
                <h1 className="text-2xl font-bold mb-2 text-center">{content.title}</h1>
                <p className="text-sm text-gray-500 mb-8 text-center">{content.last_updated}</p>
                <p className="text-gray-600 mb-8">{content.intro}</p>

                {content.sections.map((section) => (
                    <section key={section.heading} className="mb-6">
                        <h2 className="text-lg font-semibold mb-2">{section.heading}</h2>
                        <p className="text-gray-600">{section.body}</p>
                    </section>
                ))}

                <Link href="/" className="block text-center text-blue-700 hover:text-blue-500 underline mt-4">{content.return_home}</Link>
            </div>
        </main>
    );
}
