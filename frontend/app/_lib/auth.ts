import { cookies } from "next/headers";

import { serverFetch } from "./server-fetch";

export type CurrentUser = {
    twitch_id: number;
    username: string;
    display_name: string;
    email: string;
    is_twitch_excluded: boolean;
};

export async function getCurrentUser(): Promise<CurrentUser | null> {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const cookieHeader = (await cookies()).toString();
    if (!cookieHeader) {
        return null;
    }

    // Only a real 401/4xx from the backend means "not authenticated". Network
    // errors are not "logged out" - swallowing them used to mistranslate a
    // backend hiccup into a redirect to /login. Let serverFetch retry the
    // transient connection failures and propagate anything that truly fails.
    const response = await serverFetch(`${apiBase}/auth/currentuser/`, {
        headers: { cookie: cookieHeader },
        cache: "no-store",
    });
    if (!response.ok) {
        return null;
    }
    return await response.json();
}
