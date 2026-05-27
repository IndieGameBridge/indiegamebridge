"use server";

import { serverFetch } from "../_lib/server-fetch";
import type { StreamerData } from "../_components/SearchStreamerResultsList";

type SearchResponse = {
    filters: Record<string, unknown>;
    results: StreamerData[];
    total: number;
};

export async function loadStreamersPage(searchQuery: string, page: number): Promise<SearchResponse> {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const params = new URLSearchParams(searchQuery);
    params.set("p", String(page));
    const res = await serverFetch(`${apiBase}/streamers/?${params.toString()}`);
    if (!res.ok) {
        throw new Error(`Streamer search request failed (status ${res.status})`);
    }
    return await res.json();
}
