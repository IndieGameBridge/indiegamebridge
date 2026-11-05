import { jsonLd } from "../_lib/json-ld";

export type FaqContent = {
    title: string;
    items: { question: string; answer: string }[];
};

/** A page's questions and answers, with the structured data that describes them. */
export function FaqSection({ faq }: { faq: FaqContent }) {
    const faqJsonLd = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        mainEntity: faq.items.map((item) => ({
            "@type": "Question",
            name: item.question,
            acceptedAnswer: {
                "@type": "Answer",
                text: item.answer,
            },
        })),
    };

    return (
        <section className="mt-24">
            <script
                type="application/ld+json"
                dangerouslySetInnerHTML={{ __html: jsonLd(faqJsonLd) }}
            />
            <h2 className="text-2xl font-bold mb-8">{faq.title}</h2>
            <dl className="grid grid-cols-1 gap-8">
                {faq.items.map((item) => (
                    <div key={item.question}>
                        <dt className="font-semibold mb-2">{item.question}</dt>
                        <dd>{item.answer}</dd>
                    </div>
                ))}
            </dl>
        </section>
    );
}
