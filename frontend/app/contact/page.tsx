import { Fragment } from "react/jsx-runtime";
import type { Metadata } from "next";

import { getCurrentUser } from "../_lib/auth";
import { serverFetch } from "../_lib/server-fetch";
import { PageHeader, PageFooter, PageFooterContent } from "../_components";
import { ContactForm } from "./_components/ContactForm";

// Reads auth cookies + live backend data per request, so never prerender at
// build time (the backend isn't reachable then). Render on demand on the Worker.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
    title: "Contact — IndieGameBridge",
    robots: { index: false, follow: false },
};

export type ContactFormCopy = {
    name_label: string;
    name_placeholder: string;
    email_label: string;
    email_placeholder: string;
    subject_label: string;
    subject_placeholder: string;
    message_label: string;
    message_placeholder: string;
    submit_text: string;
    sending_text: string;
    success_text: string;
    error_text: string;
    validation_text: string;
    captcha_text: string;
};

export type ContactPageContent = {
    title: string;
    intro_title: string;
    intro_content: string;
    form: ContactFormCopy;
    footer_content: PageFooterContent;
};

export default async function ContactPage() {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const [response, user] = await Promise.all([
        serverFetch(`${apiBase}/pages/contact/`),
        getCurrentUser(),
    ]);

    if (!response.ok) {
        throw new Error(`Failed to load contact page content (status ${response.status})`);
    }

    const content: ContactPageContent = await response.json();

    // Public site key; safe to expose. Absent in dev → widget is skipped.
    const turnstileSiteKey = process.env.TURNSTILE_SITE_KEY ?? "";

    return (
        <Fragment>
            <PageHeader user={user} title={content.title} />

            <main className="flex-1">
                <section className="px-6">
                    <div className="max-w-[1000] mx-auto py-24">
                        <h2 className="text-2xl font-bold mb-8">{content.intro_title}</h2>
                        <p className="text-gray-600 mb-8">{content.intro_content}</p>
                        <ContactForm copy={content.form} turnstileSiteKey={turnstileSiteKey} />
                    </div>
                </section>
            </main>

            <PageFooter content={content.footer_content} />
        </Fragment>
    );
}
