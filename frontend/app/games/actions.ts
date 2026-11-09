"use server";

import { serverFetch } from "../_lib/server-fetch";
import type { GameHoursResponse } from "./_components/types";

export async function loadGameHours(gameId: number, peak: string): Promise<GameHoursResponse> {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const params = new URLSearchParams({ peak });
    const res = await serverFetch(`${apiBase}/games/${gameId}/hours/?${params.toString()}`);
    if (!res.ok) {
        throw new Error(`Game hours request failed (status ${res.status})`);
    }
    return await res.json();
}
