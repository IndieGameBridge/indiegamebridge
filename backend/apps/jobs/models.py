from django.db import models
from django.utils import timezone


class JobRun(models.Model):
    """One run of a scheduled management command: when it ran, how long it took, and
    what it did. fetch_twitch_streams keeps records of its own, FetchRun.

    The row is created as the run starts, so a run that never finishes (the process
    was killed, say) still shows up: it stays RUNNING, with no finished_at.
    """

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    job = models.CharField(
        max_length=64,
        help_text="The management command that ran.",
    )

    arguments = models.CharField(
        max_length=255,
        blank=True,
        help_text="What followed the command's name on the command line, when it was run from manage.py.",
    )

    started_at = models.DateTimeField(
        db_index=True,
        help_text="When the run started.",
    )

    finished_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the run ended; empty while it runs, and for a run that never finished.",
    )

    duration_seconds = models.FloatField(
        null=True,
        blank=True,
        help_text="From start to end.",
    )

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.RUNNING,
        help_text="FAILED when the run raised; see the error.",
    )

    counts = models.JSONField(
        default=dict,
        blank=True,
        help_text="What the run did, as the job counts it: streams approved, months archived and so on.",
    )

    output = models.TextField(
        blank=True,
        help_text="What the run printed, the end of it when it printed a lot.",
    )

    error = models.TextField(
        blank=True,
        help_text="The exception that stopped the run, if one did.",
    )

    class Meta:
        ordering = ("-started_at",)
        indexes = [
            models.Index(fields=["job", "started_at"], name="job_run_job_started_at_idx"),
        ]

    def __str__(self):
        return f"JobRun: {self.job} {self.started_at:%Y-%m-%d %H:%M} ({self.status})"

    def finish(self):
        """Record the run's end and duration, and whether it failed."""
        self.finished_at = timezone.now()
        self.duration_seconds = (self.finished_at - self.started_at).total_seconds()
        self.status = self.Status.FAILED if self.error else self.Status.SUCCEEDED
        self.save()
