from .base import BaseCachedPageBuilder
from .list_form import list_form_labels


class DashboardPageBuilder(BaseCachedPageBuilder):
    key = "dashboard"
    log_label = "Dashboard page"

    def build_content(self) -> dict:
        return {
            "title": f"Dashboard",
            "description": f"Your saved lists of streamers.",
            "empty_state": f"You have no lists yet. Save a search's results as a list, or start"
                f" an empty one and add streamers to it one by one.",
            "empty_state_cta": f"Search streamers",
            "new_list": {
                "open_btn": "New list",
                **list_form_labels(
                    submit_btn="Create list",
                    error="Couldn't create the list. Reload the page and try again.",
                ),
            },
        }
