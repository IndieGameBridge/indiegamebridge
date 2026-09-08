from .base import BaseCachedPageBuilder


class DashboardPageBuilder(BaseCachedPageBuilder):
    key = "dashboard"
    log_label = "Dashboard page"

    def build_content(self) -> dict:
        return {
            "title": f"Dashboard",
            "description": f"Your saved lists of streamers.",
            # Placeholder until the lists themselves land; the page is here first so
            # the route, the login gate and the nav entry can settle on their own.
            "placeholder": f"todo",
        }
