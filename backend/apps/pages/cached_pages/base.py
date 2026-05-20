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
        CachedPage.objects.update_or_create(
            key=self.key,
            defaults={"content": self.build_content()},
        )
        logger.info("%s cache updated.", self.log_label or self.key)
