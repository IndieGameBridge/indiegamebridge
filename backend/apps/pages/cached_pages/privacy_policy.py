from .base import BaseCachedPageBuilder


class PrivacyPolicyPageBuilder(BaseCachedPageBuilder):
    key = "privacy"
    log_label = "Privacy Policy page"

    def build_content(self) -> dict:
        return {
            "title": f"Privacy Policy",
            "return_home": f"Return to Home Page",
            "last_updated": f"Last updated: May 31, 2026",
            "intro": f"This Privacy Policy explains what data IndieGameBridge collects, why we"
                f" collect it, and the choices you have. IndieGameBridge helps indie game"
                f" developers discover Twitch streamers by aggregating publicly available"
                f" Twitch stream data.",
            "sections": [
                {
                    "heading": f"Data We Collect",
                    "body": f"Publicly available Twitch data: when streamers broadcast publicly"
                        f" on Twitch, we collect stream information exposed by the Twitch API,"
                        f" including the Twitch user ID, login and display name, game categories,"
                        f" viewer counts, language, and timestamps. Account data: when you sign in"
                        f" with Twitch, we receive your Twitch user ID, username, display name, and"
                        f" email address from Twitch. Usage data: unless you disable it in your"
                        f" account settings, we may collect anonymous information about which"
                        f" features you use, to help us improve the service.",
                },
                {
                    "heading": f"How We Use Data",
                    "body": f"We use this data to operate the service — letting developers search"
                        f" and view aggregated streamer statistics — to authenticate your account,"
                        f" and to improve our features. We do not sell your personal data.",
                },
                {
                    "heading": f"Legal Basis (GDPR)",
                    "body": f"For users in the EEA and UK, we process publicly available Twitch"
                        f" data on the basis of our legitimate interest in providing a discovery"
                        f" tool for indie developers. We process your account data to provide the"
                        f" service you request (account creation and login). Usage analytics are"
                        f" processed on the basis of legitimate interest and can be disabled at any"
                        f" time in your account settings.",
                },
                {
                    "heading": f"Cookies",
                    "body": f"We use strictly necessary cookies to keep you signed in"
                        f" (authentication tokens) and to protect against cross-site request"
                        f" forgery (CSRF). We do not use advertising or third-party tracking"
                        f" cookies.",
                },
                {
                    "heading": f"Third-Party Services",
                    "body": f"We rely on Twitch for authentication and as our source of stream"
                        f" data, and on IGDB for game metadata. Signing in with Twitch is also"
                        f" subject to Twitch's own privacy policy.",
                },
                {
                    "heading": f"Your Choices and Rights",
                    "body": f"Streamers can opt out at any time. Removing your Twitch ID from data"
                        f" collection — via the opt-out page or your account settings — deletes the"
                        f" data we have collected about your streams and excludes your Twitch ID"
                        f" from future collection. You can disable feature-usage analytics in your"
                        f" account settings. Depending on your location, you may have rights to"
                        f" access, correct, or delete your personal data; contact us to exercise"
                        f" them.",
                },
                {
                    "heading": f"Data Retention",
                    "body": f"We retain collected stream data while it remains useful for the"
                        f" service. When you opt out, data tied to your Twitch ID is removed, though"
                        f" copies may persist in caches for up to an hour while they refresh.",
                },
                {
                    "heading": f"Changes to This Policy",
                    "body": f"We may update this Privacy Policy from time to time. Material changes"
                        f" will be reflected by updating the date shown at the top of this page.",
                },
                {
                    "heading": f"Contact",
                    "body": f"Questions about this policy or your data can be raised via our"
                        f" GitHub repository.",
                },
            ],
        }
