export type StandoutsContent = {
    title: string;
    paragraphs: string[];
};

/** A language page's few paragraphs on how it differs from the other languages. */
export function Standouts({ standouts }: { standouts: StandoutsContent }) {
    return (
        <section className="mb-8">
            <h2 className="text-xl font-bold mb-3">{standouts.title}</h2>
            <div className="grid grid-cols-1 gap-4">
                {standouts.paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
            </div>
        </section>
    );
}
