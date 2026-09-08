from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models


hex_color_validator = RegexValidator(
    regex=r"^#[0-9a-fA-F]{6}$",
    message="Enter a colour as '#rrggbb', for example '#0072B2'.",
)


class UserLabelForListOfStreamers(models.Model):
    """A user's own colour-coded label for their lists of streamers.

    Deliberately not a generic "UserLabel" carrying a purpose field: the planned
    label for individual streamers tags a different thing and will hold its own
    foreign key. Splitting them keeps each model's relations concrete instead of
    nullable-depending-on-purpose.

    Labels are private to their owner and never shown to anyone else. Titles are
    deliberately not unique: the same word in two colours is a useful pair (a
    "priority" in red and in green, say), and the colour is half the label.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="list_labels",
        help_text="User this label belongs to; labels are private to their owner.",
    )

    title = models.CharField(
        max_length=16,
        help_text="Short label text shown on a list card, e.g. 'shooters'.",
    )

    color = models.CharField(
        max_length=7,
        validators=[hex_color_validator],
        help_text="Label colour as a '#rrggbb' hex string; drives the chip's background.",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the label was created.",
    )

    class Meta:
        # Alphabetical by default: labels are picked from a list, not ranked.
        ordering = ("title",)

    def __str__(self):
        return f"UserLabelForListOfStreamers: {self.title} ({self.color}) of {self.owner}"
