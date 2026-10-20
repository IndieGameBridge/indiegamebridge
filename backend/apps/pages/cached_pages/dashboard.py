from .base import BaseCachedPageBuilder


class DashboardPageBuilder(BaseCachedPageBuilder):
    key = "dashboard"
    log_label = "Dashboard page"

    def build_content(self) -> dict:
        return {
            "title": f"Dashboard",
            "description": f"Your saved lists of streamers.",
            "empty_state": f"You have no lists yet. Run a search, then save its results as a list"
                f" to keep them here.",
            "empty_state_cta": f"Search streamers",
        }
