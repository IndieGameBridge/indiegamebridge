from .base import BaseCachedPageBuilder


class ContactPageBuilder(BaseCachedPageBuilder):
    key = "contact"
    log_label = "Contact page"

    def build_content(self) -> dict:
        return {
            "title": f"Contact",
            "return_home": f"Return to Home Page",
            "body": f"Contact details are coming soon. In the meantime, please reach out via the project's GitHub repository.",
        }
