from .add_to_list import add_to_list_labels
from .base import BaseCachedPageBuilder
from .export_menu import export_menu_labels
from .home import HomePageBuilder
from .list_form import list_form_labels
from apps.streams.languages import PAGE_LANGUAGES, names_of
from apps.streams.search import MAX_RESULTS, StreamerSearch

# Real results a logged-out visitor sees under the demo form.
DEMO_ROWS = 10


class StreamersPageBuilder(BaseCachedPageBuilder):
    """/streamers: the search for a logged-in user, and for everyone else, search engines
    included, a page about the search with a demo of it.

    The demo's results are stored here, like the Home page's, so a logged-out request runs
    no search.
    """

    key = "streamers"
    log_label = "Streamers page"

    def build_content(self) -> dict:
        filters_config, _ = StreamerSearch.get_filters_config()
        demo_search = StreamerSearch()
        return {
            "title": "Search Streamers",
            "description": "Filter Twitch streamers by genre, language, and audience size.",
            # SEO <title> / meta description. Written for the logged-out page, the one search
            # engines see.
            "seo_title": "Search Twitch Streamers by Genre and Viewers | IndieGameBridge",
            "seo_description": "Search Twitch streamers by the genres they play, their language and their real"
                " viewers over the last 4 weeks, and find who to pitch your indie game to.",
            "public_page": self._public_page(),
            "search_form": {
                "title": "Search Streamers",
                "aria_label": "Search streamers form",
                "filters": filters_config,
                "btn_text": "Apply Filters",
                "demo_title": "Note:",
                "search_notes": [
                    "Results are based on each streamer's streams from the last 4 weeks.",
                    "Picking a second or third genre narrows the results: only streamers who"
                        " played all of the chosen genres in that window are shown.",
                ],
                "demo_note": "This form is a demo of the real search, which you can use once you log in. The results"
                    " below are real, matching the filters prefilled in the form, and updated daily.",
                "cta_link_text": "Log in to use the search",
            },
            "search_results": demo_search.results(limit=DEMO_ROWS),
            "search_total": demo_search.total(),
            "results_labels": {
                "found_count": "Found {count} streamers",
                "found_count_one": "Found 1 streamer",
                "view_profile": "View Profile",
                "login_to_view_profile": "Log in to see profile",
                "show_more": "Show More",
                "loading": "Loading...",
            },
            "add_to_list": add_to_list_labels(),
            "export": export_menu_labels(),
            "save_list": {
                "open_btn": "Save to list",
                "new_list_btn": "Save as new list",
                "existing_list_btn": "Add to an existing list",
                "new_list": {
                    "note": "Saves every streamer this search found, in the order shown. The list"
                        " is a snapshot and won't change when the search results do.",
                    **list_form_labels(
                        submit_btn="Save list",
                        error="Couldn't save the list. Reload the page and try again.",
                    ),
                },
                "existing_list": {
                    "list_label": "List",
                    "list_placeholder": "Choose a list",
                    "note": "Adds every streamer this search found to the end of the list, in the"
                        " order shown. Streamers already in it are skipped.",
                    "submit_btn": "Add to list",
                    "saving": "Adding...",
                    "cancel_btn": "Cancel",
                    "loading": "Loading your lists...",
                    "load_error": "Couldn't load your lists. Reload the page and try again.",
                    "no_lists": "You have no lists yet. Save these results as a new list instead.",
                    "error": "Couldn't add the streamers. Reload the page and try again.",
                    "done": "“{title}”: {added} added.",
                    "done_skipped": "“{title}”: {added} added, {skipped} already in the list.",
                    "open_list": "Open list",
                    "close_btn": "Close",
                },
            },
        }

    @staticmethod
    def _public_page() -> dict:
        streamers, _ = HomePageBuilder.search_window_counts()
        return {
            "title": "Search Twitch Streamers",
            "description": "Find the Twitch streamers who already play games like yours.",
            "login_note": "You need to log in with Twitch to use the search. It's free, and we never see your password.",
            "login_btn": "Log in to search",
            "about": {
                "title": "Find Twitch streamers who already play games like yours",
                "paragraphs": [
                    "This search is for indie game developers who want to pitch a game to Twitch streamers. Instead of"
                        " guessing from follower counts, you see what each streamer really did in the last 4 weeks:"
                        " which genres they played, how often they streamed, and how many viewers they had.",
                    f"It covers {HomePageBuilder.approx(streamers)} streamers who played a game on Twitch in that time,"
                        f" in {len(PAGE_LANGUAGES)} languages: {names_of(PAGE_LANGUAGES)}. So you can build a shortlist"
                        " of people whose audience already watches games like yours, at the size you want.",
                ],
            },
            "how_to": {
                "title": "How to use the streamer search",
                "steps": [
                    {
                        "title": "Log in with Twitch.",
                        "text": "It's free, and your Twitch account is all you need.",
                        "logged_out_only": True,
                    },
                    {
                        "title": "Set the filters.",
                        "text": "Pick a language, a streamer size by max viewers, and up to three game genres. You can"
                            " also narrow by average viewers, and by how many streams and hours they did in the last"
                            " 4 weeks.",
                    },
                    {
                        "title": "Read the results.",
                        "text": f"You get up to {MAX_RESULTS:,} streamers, the highest peak first.",
                    },
                    {
                        "title": "Open a profile.",
                        "text": "It shows a streamer's numbers, a day-by-day activity chart and their recent streams"
                            " with the games played in them, and it links to their Twitch channel.",
                    },
                    {
                        "title": "Save who you like.",
                        "text": "Add streamers to a list one by one or save a whole search, keep a private note on each"
                            " one, and export a list as an Excel, CSV or JSON file when you're ready to reach out.",
                    },
                ],
            },
            "numbers": {
                "title": "What the numbers in a result mean",
                "items": [
                    {
                        "term": "Peak",
                        "meaning": "The streamer's highest viewer count in the last 4 weeks. The Max Viewers filter uses"
                            " this number.",
                    },
                    {
                        "term": "Avg",
                        "meaning": "Their average viewer count across those streams. One raid can push a peak far above"
                            " the usual, so this is the steadier number.",
                    },
                    {
                        "term": "Activity",
                        "meaning": "How many streams they ran in the last 4 weeks, and how many hours those streams"
                            " lasted.",
                    },
                    {
                        "term": "Days streamed",
                        "meaning": "A column for each of the last 28 days, today first, filled if they started a stream"
                            " that day. It shows at a glance who streams regularly and who has gone quiet. Days are in"
                            " UTC, and a stream appears a few hours after it ends.",
                    },
                    {
                        "term": "Genres",
                        "meaning": "The genres of the games they played in those streams, taken from IGDB.",
                    },
                ],
                "note": "Every number is for one broadcast language, so a streamer who streams in two languages has"
                    " separate numbers in each.",
            },
            "faq": {
                "title": "Questions about the streamer search",
                "items": [
                    {
                        "question": "Do I need an account to search Twitch streamers here?",
                        "answer": "You need to log in with Twitch to use the filters, open a streamer's profile, or save"
                            " and export lists. There's no separate sign-up: your Twitch account is enough, and we use"
                            " it only to verify who you are.",
                        "logged_out_only": True,
                    },
                    {
                        "question": "Is the streamer search free?",
                        "answer": "Yes. The search, the profiles, the lists and the exports are free to use.",
                    },
                    {
                        "question": "Which streamers can I find?",
                        "answer": "Streamers who played a game on Twitch in the last 4 weeks, in one of the languages"
                            " above, with at least 3 viewers on a stream. A stream that never played a game, such as"
                            " one that stayed in Just Chatting, doesn't count.",
                    },
                    {
                        "question": "How fresh are the numbers?",
                        "answer": "We check live Twitch streams every 20 minutes, and the search's numbers are rebuilt"
                            " every 6 hours. They always cover the last 4 weeks.",
                    },
                    {
                        "question": "How do I contact a streamer?",
                        "answer": "We don't collect contact details. A streamer's profile links to their Twitch channel,"
                            " where you can look for how they like to be reached.",
                    },
                    {
                        "question": "Can a streamer be removed from the search?",
                        "answer": "Yes. A streamer can opt out at any time with the link at the bottom of this page,"
                            " which erases what we collected about them and keeps them out of future collection.",
                    },
                ],
            },
            "demo_title": "A sample search",
        }
