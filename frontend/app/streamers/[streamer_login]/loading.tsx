import { LoadingNote } from "../_components/LoadingNote";

export default function StreamerProfileLoading() {
    return (
        <main className="flex-1 px-6">
            <div className="max-w-[1000] mx-auto py-32">
                <LoadingNote text="Loading the profile…" />
            </div>
        </main>
    );
}
