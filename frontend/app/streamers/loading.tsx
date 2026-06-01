export default function StreamersLoading() {
    return (
        <main className="flex-1 px-6">
            <div className="max-w-[1000] mx-auto py-32 text-center">
                <div className="inline-flex items-center gap-3 text-brand-blue">
                    <svg
                        aria-hidden="true"
                        viewBox="0 0 24 24"
                        className="w-6 h-6 animate-spin fill-current"
                    >
                        <path d="M12 4a8 8 0 0 1 8 8h-3a5 5 0 0 0-5-5V4z" />
                    </svg>
                    <span className="text-lg">Searching streamers…</span>
                </div>
                <p className="text-sm text-gray-500 mt-4">
                    Fresh searches may take a moment. Results are cached for an hour after
                    the first run, so the next request with the same filters will be instant.
                </p>
            </div>
        </main>
    );
}
