"""IGDB API client. Uses the same Twitch OAuth flow as Helix."""

from datetime import date, datetime, timedelta, timezone

from core.utils.twitch_api_base_client import TwitchApiBaseClient


_IGDB_API_URL = "https://api.igdb.com/v4"
_APICALYPSE_HEADERS = {"Content-Type": "text/plain"}


def release_date_of(game: dict) -> date | None:
    """A game's first release date from IGDB's Unix timestamp; None when it gives none.

    Counted from the epoch, since a game from before 1970 has a negative timestamp, which
    datetime.fromtimestamp can't take on Windows.
    """
    timestamp = game.get("first_release_date")
    if timestamp is None:
        return None
    return (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=timestamp)).date()


class IgdbApiClient(TwitchApiBaseClient):
    """Client for the IGDB API.

    Note: IGDB uses Apicalypse (POST with a text body) rather than REST query
    params. Implementations of methods below should use ``self._request`` with
    ``content=<query>`` and ``headers={"Content-Type": "text/plain"}``.
    """

    def get_genres(self, limit=500, offset=0):
        query = f"fields *; limit {limit}; offset {offset};"
        resp = self._request(
            "POST",
            f"{_IGDB_API_URL}/genres/",
            content=query,
            headers=_APICALYPSE_HEADERS,
        )
        return resp.json()

    def get_games_by_ids(self, ids):
        """Fetches game metadata for a batch of host game ids.

        IGDB caps `where id = (...)` queries at 500 ids per request; the caller
        must chunk accordingly.
        """
        if not ids:
            return []
        ids_list = ",".join(str(i) for i in ids)
        query = (
            f"fields id,name,summary,url,genres,first_release_date;"
            f" where id = ({ids_list});"
            f" limit {len(ids)};"
        )
        resp = self._request(
            "POST",
            f"{_IGDB_API_URL}/games/",
            content=query,
            headers=_APICALYPSE_HEADERS,
        )
        return resp.json()
