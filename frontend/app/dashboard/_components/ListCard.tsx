import { formatDate } from "../../_lib/format";

export type ListLabel = {
    id: number;
    title: string;
    color: string;
};

export type ListCardData = {
    id: number;
    title: string;
    description: string;
    labels: ListLabel[];
    streamers_count: number;
    created_at: string;
};

// Label colours are the owner's own pick, so the chip's text follows its
// background: black once that is bright enough to out-contrast white (WCAG
// relative luminance above ~0.179), white otherwise.
function labelTextColor(hex: string): string {
    const [r, g, b] = [1, 3, 5].map((start) => {
        const channel = parseInt(hex.slice(start, start + 2), 16) / 255;
        return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.179 ? "#000000" : "#ffffff";
}

export function ListCard({ list }: { list: ListCardData }) {
    return (
        <article className="flex flex-col gap-3 min-w-0 p-4 bg-white border border-gray-300 rounded">
            <h2 className="font-bold text-lg wrap-break-word">{list.title}</h2>

            {list.description && (
                <p className="text-sm text-gray-600 line-clamp-3 wrap-break-word" title={list.description}>
                    {list.description}
                </p>
            )}

            {list.labels.length > 0 && (
                <div className="flex flex-row flex-wrap gap-1">
                    {list.labels.map((label) => (
                        <span
                            key={label.id}
                            className="py-0.5 px-2 rounded-sm text-xs"
                            style={{ backgroundColor: label.color, color: labelTextColor(label.color) }}
                        >
                            {label.title}
                        </span>
                    ))}
                </div>
            )}

            <div className="mt-auto pt-3 border-t border-t-gray-300 flex flex-row flex-wrap justify-between gap-x-4 text-xs">
                <span><span className="text-brand-blue uppercase">Streamers: </span>{list.streamers_count.toLocaleString()}</span>
                <span><span className="text-brand-blue uppercase">Created: </span>{formatDate(list.created_at)}</span>
            </div>
        </article>
    );
}
