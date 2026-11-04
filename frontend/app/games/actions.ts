"use server";

import { serverFetch } from "../_lib/server-fetch";
import type { GameHoursResponse, GameSearchResponse } from "./_components/types";

export async function loadGamesPage(apiQuery: string, page: number): Promise<GameSearchResponse> {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const params = new URLSearchParams(apiQuery);
    params.set("p", String(page));
    const res = await serverFetch(`${apiBase}/games/?${params.toString()}`);
    if (!res.ok) {
        throw new Error(`Game search request failed (status ${res.status})`);
    }
    return await res.json();
}

export async function loadGameHours(gameId: number, peak: string): Promise<GameHoursResponse> {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const params = new URLSearchParams({ peak });
    const res = await serverFetch(`${apiBase}/games/${gameId}/hours/?${params.toString()}`);
    if (!res.ok) {
        throw new Error(`Game hours request failed (status ${res.status})`);
    }
    return await res.json();
}
