from django.db import models
from django.utils import timezone


class FetchRun(models.Model):
    """One run of fetch_twitch_streams: when it ran, how long it took, and what it wrote.

    The row is created as the run starts, so a run that never finishes (the process
    was killed, say) still shows up: it stays RUNNING, with no finished_at.
    """

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

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
        help_text="From start to end, finalizing ended streams included.",
    )

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.RUNNING,
        help_text="FAILED when any language's polling raised, or the run itself did; see the errors.",
    )

    time_limit_hit = models.BooleanField(
        default=False,
        help_text="Whether any language stopped at the run's time limit with streams left unpolled.",
    )

    streams_collected = models.PositiveIntegerField(
        default=0,
        help_text="Streams written across all languages: new ones, plus live ones given another snapshot.",
    )

    streams_finalized = models.PositiveIntegerField(
        default=0,
        help_text="Streams that had ended, marked offline with their summary fields computed.",
    )

    streams_dropped = models.PositiveIntegerField(
        default=0,
        help_text="Streams that had ended, deleted for too little data: one snapshot, or under 3 viewers.",
    )

    finalize_seconds = models.FloatField(
        null=True,
        blank=True,
        help_text="Time spent finalizing the ended streams.",
    )

    error = models.TextField(
        blank=True,
        help_text="The exception that stopped the run, if one did. A language's own failure is on its row.",
    )

    class Meta:
        ordering = ("-started_at",)

    def __str__(self):
        return f"FetchRun: {self.started_at:%Y-%m-%d %H:%M} ({self.status})"

    def finish(self):
        """Record the run's end and duration, and whether anything in it failed."""
        self.finished_at = timezone.now()
        self.duration_seconds = (self.finished_at - self.started_at).total_seconds()
        failed = self.error or self.languages.exclude(error="").exists()
        self.status = self.Status.FAILED if failed else self.Status.SUCCEEDED
        self.save()


class FetchRunLanguage(models.Model):
    """One language's polling within a FetchRun.

    The counts cover the poll rounds whose writes were committed; when a round
    raises, the row keeps everything done before it, along with the error.
    """

    run = models.ForeignKey(
        FetchRun,
        on_delete=models.CASCADE,
        related_name="languages",
    )

    language = models.CharField(
        max_length=8,
        help_text="ISO 639-1 code of the language polled.",
    )

    duration_seconds = models.FloatField(
        null=True,
        blank=True,
        help_text="From the start of the language's polling to its end, rate-limit sleeps included.",
    )

    rounds = models.PositiveIntegerField(
        default=0,
        help_text="Poll rounds: a batch of Helix pages, then the database write of their streams.",
    )

    requests = models.PositiveIntegerField(
        default=0,
        help_text="Helix requests sent, retries included.",
    )

    helix_seconds = models.FloatField(
        default=0,
        help_text="Time spent waiting on Helix.",
    )

    write_seconds = models.FloatField(
        default=0,
        help_text="Time spent writing streams to the database.",
    )

    streams_fetched = models.PositiveIntegerField(
        default=0,
        help_text="Streams Helix returned: the excluded, the duplicates and the written together.",
    )

    streams_excluded = models.PositiveIntegerField(
        default=0,
        help_text="Streams skipped because their streamer opted out.",
    )

    streams_duplicates = models.PositiveIntegerField(
        default=0,
        help_text="Streams skipped because the run had seen them already: pages shift as viewer counts change.",
    )

    streams_written = models.PositiveIntegerField(
        default=0,
        help_text="Streams written: the created ones, plus live ones given another snapshot.",
    )

    streams_created = models.PositiveIntegerField(
        default=0,
        help_text="Streams seen for the first time.",
    )

    profiles_created = models.PositiveIntegerField(
        default=0,
        help_text="Streamers seen for the first time.",
    )

    time_limit_hit = models.BooleanField(
        default=False,
        help_text="Whether polling stopped at the run's time limit with streams left unpolled.",
    )

    rounds_detail = models.JSONField(
        default=list,
        blank=True,
        help_text="One entry per round: requests, fetched, written, helix_seconds and write_seconds.",
    )

    error = models.TextField(
        blank=True,
        help_text="The exception that stopped the language's polling, if one did.",
    )

    class Meta:
        ordering = ("run", "language")
        constraints = [
            models.UniqueConstraint(fields=["run", "language"], name="unique_fetch_run_language"),
        ]

    def __str__(self):
        return f"FetchRunLanguage: {self.language} ({self.streams_written} streams)"

    def add_round(self, *, requests, fetched, excluded, duplicates, created, profiles_created, helix_seconds, write_seconds):
        """Add one committed poll round's counts and timings."""
        written = fetched - excluded - duplicates
        self.rounds += 1
        self.requests += requests
        self.helix_seconds += helix_seconds
        self.write_seconds += write_seconds
        self.streams_fetched += fetched
        self.streams_excluded += excluded
        self.streams_duplicates += duplicates
        self.streams_written += written
        self.streams_created += created
        self.profiles_created += profiles_created
        self.rounds_detail.append({
            "requests": requests,
            "fetched": fetched,
            "written": written,
            "helix_seconds": round(helix_seconds, 2),
            "write_seconds": round(write_seconds, 2),
        })
