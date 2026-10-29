from .base import BaseCachedPageBuilder


class PrivacyPolicyPageBuilder(BaseCachedPageBuilder):
    key = "privacy"
    log_label = "Privacy Policy page"

    def build_content(self) -> dict:
        return {
            "title": f"Privacy Policy",
            "description": f"How IndieGameBridge collects, uses, and protects your data.",
            "return_home": f"Return to Home Page",
            "contact_link_text": f"Contact page",
            "last_updated": f"Last updated: October 29, 2026",
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
                        f" with Twitch, we receive your Twitch user ID, username, and display name"
                        f" from Twitch. We do not request your email address from Twitch. Usage data:"
                        f" unless you disable it in your"
                        f" account settings, we record which features you use, such as the lists"
                        f" and searches you export, to help us improve the service. Sign-in records:"
                        f" under the same setting, each time you sign in we record the time and your"
                        f" IP address, and may look up an approximate location for that address"
                        f" (country, region, and city). Contact messages: when you write to us"
                        f" through the contact form, we store your name, email address, and message,"
                        f" along with your IP address and browser type to deal with spam and abuse.",
                },
                {
                    "heading": f"How We Use Data",
                    "body": f"We use this data to operate the service — letting developers search"
                        f" and view aggregated streamer statistics — to authenticate your account,"
                        f" and to improve our features. We do not sell your personal data.",
                },
                {
                    "heading": f"Your Lists and Exports",
                    "body": f"Lists you save, and the notes you write in them, are private to your"
                        f" account and are deleted with it. If a streamer in one of your lists opts"
                        f" out, their details are removed from the list, but your note on them stays."
                        f" Files you export from a list or a search are copies made at that moment:"
                        f" a streamer's later opt-out removes their data from IndieGameBridge, but"
                        f" not from files already downloaded.",
                },
                {
                    "heading": f"Legal Basis (GDPR)",
                    "body": f"For users in the EEA and UK, we process publicly available Twitch"
                        f" data on the basis of our legitimate interest in providing a discovery"
                        f" tool for indie developers. We process your account data to provide the"
                        f" service you request (account creation and login). Usage analytics and"
                        f" sign-in records are processed on the basis of our legitimate interest in"
                        f" understanding how, and from where, the service is used, and can be"
                        f" disabled at any time in your account settings. Contact messages are"
                        f" processed on the basis of our legitimate interest in answering them and"
                        f" keeping the form free of spam.",
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
                        f" subject to Twitch's own privacy policy. To find a sign-in's approximate"
                        f" location, we send its IP address to ipinfo.io. The contact form is"
                        f" protected from bots by Cloudflare Turnstile, and the site is hosted by"
                        f" Cloudflare and DigitalOcean. Some of these services are based in the"
                        f" United States, so data they handle may be processed there.",
                },
                {
                    "heading": f"Your Choices and Rights",
                    "body": f"Streamers can opt out at any time. Removing your Twitch ID from data"
                        f" collection — via the opt-out page or your account settings — deletes the"
                        f" data we have collected about your streams and excludes your Twitch ID"
                        f" from future collection. You do not need an account to opt out, and"
                        f" opting out from the opt-out page does not create one. To re-enable"
                        f" collection later, log in with Twitch (which creates an account) and turn"
                        f" tracking back on in your account settings. You can disable feature-usage"
                        f" analytics in your account settings. You can also permanently delete your"
                        f" account at any time from your account settings; this removes your account,"
                        f" settings, and Twitch login link, and you can optionally choose to also"
                        f" delete the streams data tied to your Twitch ID at the same time."
                        f" Depending on your location, you may"
                        f" have rights to access, correct, or delete your personal data; contact us"
                        f" to exercise them. You can also lodge a complaint with your local data"
                        f" protection authority.",
                },
                {
                    "heading": f"Data Retention",
                    "body": f"We retain collected stream data while it remains useful for the"
                        f" service; streams older than two to three months move from our database to"
                        f" archive files. When you opt out, data tied to your Twitch ID is removed"
                        f" from the database right away, though copies may persist in caches for up"
                        f" to an hour while they refresh. It is removed from the archive files within"
                        f" a week, and from backups of them when those are next replaced. Account"
                        f" data is kept until you delete your account, after which your account,"
                        f" settings, and Twitch login link are removed. Usage and sign-in records"
                        f" are deleted after 12 months, or sooner if you delete your account."
                        f" Contact messages are deleted after 12 months; ask through the contact"
                        f" page if you want yours deleted sooner.",
                },
                {
                    "heading": f"Changes to This Policy",
                    "body": f"We may update this Privacy Policy from time to time. Material changes"
                        f" will be reflected by updating the date shown at the top of this page.",
                },
                {
                    "heading": f"Contact",
                    "body": f"For questions about this policy or your data, please reach out"
                        f" through our %contact_link%. Our GitHub repository remains available as a"
                        f" secondary channel.",
                },
            ],
        }
