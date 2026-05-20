from .base import BaseCachedPageBuilder


class PageFooterBuilder(BaseCachedPageBuilder):
    key = "page_footer"
    log_label = "Page footer"

    def build_content(self) -> dict:
        return {
            "data_source": f"Data sourced from public Twitch streams. Streamers can %opt_out_link% at any time.",
            "opt_out_text": "opt out",
            "footer_links": [
                {
                    "text": "Request removal",
                    "url": "/optout",
                    "nofollow": 1,
                    "is_internal": 1,
                },
                {
                    "text": "GitHub",
                    "url": "/https://github.com/IndieGameBridge/indiegamebridge",
                    "nofollow": 1,
                    "is_internal": 0,
                },
                {
                    "text": "Contact",
                    "url": "/contact",
                    "nofollow": 1,
                    "is_internal": 1,
                },
            ],
        }
