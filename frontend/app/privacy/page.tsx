import { Fragment } from "react/jsx-runtime";
import type { Metadata } from "next";
import Link from "next/link";

import { getCurrentUser } from "../_lib/auth";
import { serverFetch } from "../_lib/server-fetch";
import { PageHeader, PageFooter, PageFooterContent } from "../_components";

export const metadata: Metadata = {
    title: "Privacy Policy — IndieGameBridge",
    // A privacy policy is a public legal page, so unlike the other secondary
    // pages it's left indexable/followable.
    robots: { index: true, follow: true },
};

export type PrivacyPolicyPageContent = {
    title: string;
    contact_link_text: string;
    last_updated: string;
    intro: string;
    sections: { heading: string; body: string }[];
    footer_content: PageFooterContent;
};

export default async function PrivacyPolicyPage() {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const [response, user] = await Promise.all([
        serverFetch(`${apiBase}/pages/privacy/`),
        getCurrentUser(),
    ]);

    if (!response.ok) {
        throw new Error(`Failed to load privacy policy page content (status ${response.status})`);
    }

    const content: PrivacyPolicyPageContent = await response.json();

    return (
        <Fragment>
            <PageHeader user={user} title={content.title} />

            <main className="flex-1">
                <section className="px-6">
                    <div className="max-w-[1000] mx-auto py-24">
                        <p className="text-sm text-gray-500 mb-8">{content.last_updated}</p>
                        <p className="text-gray-600 mb-8">{content.intro}</p>

                        {content.sections.map((section) => (
                            <section key={section.heading} className="mb-6">
                                <h2 className="text-lg font-semibold mb-2">{section.heading}</h2>
                                <p className="text-gray-600">
                                    {section.body.split("%contact_link%").map((part, i, arr) => (
                                        <Fragment key={i}>
                                            {part}
                                            {i < arr.length - 1 && (
                                                <Link href="/contact" className="text-blue-700 hover:text-blue-500 underline">{content.contact_link_text}</Link>
                                            )}
                                        </Fragment>
                                    ))}
                                </p>
                            </section>
                        ))}
                    </div>
                </section>
            </main>

            <PageFooter content={content.footer_content} />
        </Fragment>
    );
}
