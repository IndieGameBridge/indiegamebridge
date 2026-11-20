"""Finding a streamer's profile from what someone types or pastes: a Twitch login, "@login"
or a link to the channel."""

import re

from apps.streams.models import StreamerProfile

# Twitch logins: letters, digits and underscores, 25 at most, always lowercase.
TWITCH_LOGIN = re.compile(r"[a-z0-9_]{1,25}")

# A channel link, with or without https://, www. or m., and whatever follows the login,
# such as /videos or ?sr=a.
CHANNEL_LINK = re.compile(r"(?:https?://)?(?:www\.|m\.)?twitch\.tv/([^/?#\s]*)", re.IGNORECASE)

# Far longer than any login or channel link, so longer text is neither.
MAX_TEXT_LENGTH = 200


def twitch_login_from(text: str) -> str | None:
    """The Twitch login in a login, "@login" or channel link; None when the text holds none.

    "Shroud", "@shroud", "twitch.tv/shroud" and "https://www.twitch.tv/shroud/videos" all
    give "shroud".
    """
    text = text.strip()
    if len(text) > MAX_TEXT_LENGTH:
        return None
    link = CHANNEL_LINK.match(text)
    login = (link.group(1) if link else text.removeprefix("@")).lower()
    return login if TWITCH_LOGIN.fullmatch(login) else None


def profile_for_login(login: str) -> StreamerProfile | None:
    """The Twitch streamer with this login.

    Twitch can give a freed login to a new account, so a few logins belong to two profiles.
    The older one is taken, the same one every time.
    """
    return StreamerProfile.objects.filter(host=StreamerProfile.Host.TWITCH, host_login=login).first()
