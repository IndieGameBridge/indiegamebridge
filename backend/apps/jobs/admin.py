from datetime import timedelta

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.urls import path
from django.utils.html import format_html

from apps.jobs.busy_time import busy_time
from apps.jobs.cron import JOBS_BY_NAME
from apps.jobs.graphs import job_graphs
from apps.jobs.models import JobRun
from core.utils.admin_charts import GraphsAdminMixin
from core.utils.admin_export import CsvExportAdminMixin, last_line, seconds, utc_minute


@admin.register(JobRun)
class JobRunAdmin(CsvExportAdminMixin, GraphsAdminMixin, admin.ModelAdmin):
    """View only: the scheduled commands write these as they run. Graphs of them, and the
    minutes they took, are a link away from the list, and the newest can be exported."""

    change_list_template = "admin/jobs/jobrun/change_list.html"
    export_name = "job-runs"
    graphs_title = "Job run graphs"
    list_display = ("started_at", "job", "arguments", "status", "duration", "what_it_did")
    list_filter = ("job", "status")
    date_hierarchy = "started_at"
    fields = (
        "job", "arguments", "status", "started_at", "finished_at", "duration", "what_it_did", "printed", "error",
    )
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Duration", ordering="duration_seconds")
    def duration(self, obj):
        # 312.4 -> "0:05:12", as the archive commands print their run time; empty until set
        return "" if obj.duration_seconds is None else str(timedelta(seconds=round(obj.duration_seconds)))

    @admin.display(description="What it did")
    def what_it_did(self, obj):
        """The run's counts, labelled as the job's graphs label them, in the same order."""
        job = JOBS_BY_NAME.get(obj.job)
        labels = dict(job.counts) if job else {}
        return "; ".join(f"{labels.get(key, key)}: {value:,}" for key, value in _counts_in_order(obj))

    @admin.display(description="Output")
    def printed(self, obj):
        return format_html('<pre style="margin: 0; white-space: pre-wrap">{}</pre>', obj.output)

    def graphs_context(self, request, days):
        return job_graphs(days, job=request.GET.get("job", ""))

    def export_rows(self, size):
        """The newest runs of every job, with their counts and, for a failure, what failed.
        What a run printed stays out: it can run to pages."""
        header = ["job", "arguments", "status", "started_at_utc", "duration_seconds", "counts", "error"]
        return header, [
            [
                run.job,
                run.arguments,
                run.status,
                utc_minute(run.started_at),
                seconds(run.duration_seconds),
                "; ".join(f"{key}={value}" for key, value in _counts_in_order(run)),
                last_line(run.error),
            ]
            for run in JobRun.objects.defer("output").order_by("-started_at")[:size]
        ]

    def get_urls(self):
        # Ahead of the ModelAdmin's own, whose <object_id>/ would take it for an id.
        return [
            path("busy-time/", self.admin_site.admin_view(self.busy_time_view), name="jobs_jobrun_busy_time"),
            *super().get_urls(),
        ]

    def busy_time_view(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied
        return self.chart_page(request, "Busy time", busy_time(request.GET.get("offset")))


def _counts_in_order(run) -> list[tuple[str, int]]:
    """A run's counts in the order its job declares them, and any it doesn't after them.
    Stored as jsonb, they'd come back in Postgres's own key order."""
    job = JOBS_BY_NAME.get(run.job)
    declared = [key for key, _ in job.counts] if job else []
    keys = [key for key in declared if key in run.counts] + [key for key in run.counts if key not in declared]
    return [(key, run.counts[key]) for key in keys]
