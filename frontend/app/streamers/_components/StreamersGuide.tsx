import { Fragment } from "react/jsx-runtime";

import { FaqContent, FaqSection } from "../../_components";

type LoggedOutOnly = {
    // Asks the reader to do what a logged-in user has already done.
    logged_out_only?: boolean;
};

export type StreamersGuideCopy = {
    about: { title: string; paragraphs: string[] };
    how_to: { title: string; steps: ({ title: string; text: string } & LoggedOutOnly)[] };
    numbers: { title: string; items: { term: string; meaning: string }[]; note: string };
    faq: { title: string; items: (FaqContent["items"][number] & LoggedOutOnly)[] };
};

/**
 * What the search is for and how to use it. A logged-out visitor reads it before the demo;
 * a logged-in user finds it under the results.
 */
export function StreamersGuide({ copy, logged_in = false }: { copy: StreamersGuideCopy; logged_in?: boolean }) {
    const forReader = <Item extends LoggedOutOnly>(items: Item[]) =>
        logged_in ? items.filter((item) => !item.logged_out_only) : items;

    return (
        <Fragment>
            <h2 className="text-2xl font-bold mb-8">{copy.about.title}</h2>
            <div className="grid grid-cols-1 gap-6">
                {copy.about.paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
            </div>

            <section className="mt-24">
                <h2 className="text-2xl font-bold mb-8">{copy.how_to.title}</h2>
                <ol className="list-decimal pl-6 grid grid-cols-1 gap-4">
                    {forReader(copy.how_to.steps).map((step) => (
                        <li key={step.title}>
                            <span className="font-semibold">{step.title}</span> {step.text}
                        </li>
                    ))}
                </ol>
            </section>

            <section className="mt-24">
                <h2 className="text-2xl font-bold mb-8">{copy.numbers.title}</h2>
                <dl className="grid grid-cols-1 gap-8">
                    {copy.numbers.items.map((item) => (
                        <div key={item.term}>
                            <dt className="font-semibold mb-2">{item.term}</dt>
                            <dd>{item.meaning}</dd>
                        </div>
                    ))}
                </dl>
                <p className="mt-8">{copy.numbers.note}</p>
            </section>

            <FaqSection faq={{ title: copy.faq.title, items: forReader(copy.faq.items) }} />
        </Fragment>
    );
}
