import Link from "next/link";

import { formatDate } from "../../_lib/format";
import { LabelChip, ListLabel } from "../../_components";

export type ListCardData = {
    id: number;
    title: string;
    description: string;
    labels: ListLabel[];
    streamers_count: number;
    created_at: string;
};

export function ListCard({ list }: { list: ListCardData }) {
    return (
        <Link
            href={`/lists/${list.id}`}
            className="flex flex-col gap-3 min-w-0 p-4 bg-white border border-gray-300 rounded hover:border-gray-500"
        >
            <h2 className="font-bold text-lg wrap-break-word">{list.title}</h2>

            {list.description && (
                <p className="text-sm text-gray-600 line-clamp-3 wrap-break-word" title={list.description}>
                    {list.description}
                </p>
            )}

            {list.labels.length > 0 && (
                <div className="flex flex-row flex-wrap gap-1">
                    {list.labels.map((label) => <LabelChip key={label.id} label={label} />)}
                </div>
            )}

            <div className="mt-auto pt-3 border-t border-t-gray-300 flex flex-row flex-wrap justify-between gap-x-4 text-xs">
                <span><span className="text-brand-blue uppercase">Streamers: </span>{list.streamers_count.toLocaleString()}</span>
                <span><span className="text-brand-blue uppercase">Created: </span>{formatDate(list.created_at)}</span>
            </div>
        </Link>
    );
}
