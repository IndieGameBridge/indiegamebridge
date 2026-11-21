import { Fragment } from "react/jsx-runtime";

import { FaqContent, FaqSection } from "../../_components";

export type GamesGuideCopy = {
    title: string;
    steps: { title: string; text: string }[];
};

/** How to read and narrow the Games list, under it, and on the overview its questions. */
export function GamesGuide({ guide, faq }: { guide: GamesGuideCopy; faq: FaqContent | null }) {
    return (
        <Fragment>
            <h2 className="text-2xl font-bold mb-8">{guide.title}</h2>
            <ol className="list-decimal pl-6 grid grid-cols-1 gap-4">
                {guide.steps.map((step) => (
                    <li key={step.title}>
                        <span className="font-semibold">{step.title}</span> {step.text}
                    </li>
                ))}
            </ol>
            {faq && <FaqSection faq={faq} />}
        </Fragment>
    );
}
