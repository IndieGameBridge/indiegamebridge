from django.contrib import admin
from django.utils.html import format_html

from apps.userlists.models import UserLabelForListOfStreamers, UserListOfStreamers


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


@admin.register(UserListOfStreamers)
class UserListOfStreamersAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "label_titles", "created_at")
    search_fields = ("title", "owner__username")
    list_select_related = ("owner",)
    ordering = ("owner", "-created_at")
    readonly_fields = ("created_at", "updated_at")
    filter_horizontal = ("labels",)

    def get_queryset(self, request):
        # label_titles walks the M2M for every row; prefetch so the changelist
        # stays one extra query rather than one per list.
        return super().get_queryset(request).prefetch_related("labels")

    @admin.display(description="Labels")
    def label_titles(self, obj):
        return ", ".join(label.title for label in obj.labels.all()) or "-"
