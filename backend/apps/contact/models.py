from django.db import models


class ContactMessage(models.Model):
    """A message submitted through the public contact form.

    We persist every submission rather than emailing it: the inbox lives in
    the Django admin. Cloudflare Email Routing can forward inbound mail to a
    personal inbox but cannot send outbound, so there's no SMTP path here by
    design - read submissions in admin instead.
    """

    name = models.CharField(max_length=120)
    email = models.EmailField(max_length=254)
    subject = models.CharField(max_length=200, blank=True)
    message = models.TextField(max_length=5000)

    created_at = models.DateTimeField(auto_now_add=True)
    # Captured for abuse triage only (rate-limit offenders, spam waves).
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} <{self.email}> - {self.created_at:%Y-%m-%d %H:%M}"
