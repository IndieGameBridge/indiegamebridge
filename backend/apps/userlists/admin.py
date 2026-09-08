from django.contrib import admin
from django.utils.html import format_html

from apps.userlists.models import UserLabelForListOfStreamers


@admin.register(UserLabelForListOfStreamers)
class UserLabelForListOfStreamersAdmin(admin.ModelAdmin):
    list_display = ("title", "swatch", "owner", "created_at")
    search_fields = ("title", "owner__username")
    list_select_related = ("owner",)
    ordering = ("owner", "title")
    readonly_fields = ("created_at",)

    @admin.display(description="Colour", ordering="color")
    def swatch(self, obj):
        # The hex value alone is unreadable at a glance; the chip is the point.
        return format_html(
            '<span style="display:inline-block;width:2.5em;height:1em;'
            'border:1px solid #999;background:{}"></span> {}',
            obj.color,
            obj.color,
        )
