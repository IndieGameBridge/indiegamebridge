/** A spinner with a line of text, for what a Streamers route shows while it loads. */
export function LoadingNote({ text, note }: { text: string; note?: string }) {
    return (
        <div className="text-center">
            <div className="inline-flex items-center gap-3 text-brand-blue">
                <svg
                    aria-hidden="true"
                    viewBox="0 0 24 24"
                    className="w-6 h-6 animate-spin fill-current"
                >
                    <path d="M12 4a8 8 0 0 1 8 8h-3a5 5 0 0 0-5-5V4z" />
                </svg>
                <span className="text-lg">{text}</span>
            </div>
            {note && <p className="text-sm text-gray-500 mt-4">{note}</p>}
        </div>
    );
}
