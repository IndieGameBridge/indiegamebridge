from .base import BaseCachedPageBuilder


class ContactPageBuilder(BaseCachedPageBuilder):
    key = "contact"
    log_label = "Contact page"

    def build_content(self) -> dict:
        return {
            "title": f"Contact",
            "return_home": f"Return to Home Page",
            "intro_title": f"Have a question or feedback?",
            "intro_content": f" Send us a message and we'll get back to you. You can also reach us"
                f" through the project's GitHub repository.",
            "form": {
                "name_label": f"Name",
                "name_placeholder": f"Your name",
                "email_label": f"Email",
                "email_placeholder": f"you@example.com",
                "subject_label": f"Subject",
                "subject_placeholder": f"What's this about? (optional)",
                "message_label": f"Message",
                "message_placeholder": f"Write your message here...",
                "submit_text": f"Send message",
                "sending_text": f"Sending...",
                "success_text": f"Thanks! Your message has been received."
                    f" We'll get back to you soon.",
                "error_text": f"Something went wrong sending your message."
                    f" Please try again, or reach out via our GitHub repository.",
                "validation_text": f"Please fill in your name, a valid email, and a message.",
                "captcha_text": f"Please complete the verification below.",
            },
        }
