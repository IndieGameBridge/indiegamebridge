from django.contrib import admin

from apps.contact.models import ContactMessage


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "subject", "created_at")
    search_fields = ("name", "email", "subject", "message")
    list_filter = ("created_at",)
    readonly_fields = (
        "name",
        "email",
        "subject",
        "message",
        "created_at",
        "ip_address",
        "user_agent",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        # Submissions only ever arrive through the public form.
        return False
