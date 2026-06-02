import logging
from abc import ABC, abstractmethod

from apps.pages.models import CachedPage

logger = logging.getLogger(__name__)


class BaseCachedPageBuilder(ABC):
    key: str = ""
    log_label: str = ""

    @abstractmethod
    def build_content(self) -> dict:
        ...

    def run(self) -> None:
        # Only write (and so bump updated_at) when the payload actually changed.
        # The command rebuilds every page each run, but most pages are static;
        # bumping updated_at unconditionally would give them a misleading
        # "freshness" that consumers like the sitemap's <lastmod> rely on.
        content = self.build_content()
        label = self.log_label or self.key

        page = CachedPage.objects.filter(key=self.key).first()
        if page is None:
            CachedPage.objects.create(key=self.key, content=content)
            logger.info("%s cache created.", label)
        elif page.content != content:
            page.content = content
            page.save(update_fields=["content", "updated_at"])
            logger.info("%s cache updated.", label)
        else:
            logger.info("%s cache unchanged.", label)
