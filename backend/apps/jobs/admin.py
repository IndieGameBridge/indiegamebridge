from datetime import timedelta

from django.contrib import admin
from django.utils.html import format_html

from apps.jobs.cron import JOBS_BY_NAME
from apps.jobs.graphs import job_graphs
from apps.jobs.models import JobRun
from core.utils.admin_charts import GraphsAdminMixin


@admin.register(JobRun)
class JobRunAdmin(GraphsAdminMixin, admin.ModelAdmin):
    """View only: the scheduled commands write these as they run. Graphs of them are a
    link away from the list."""

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
        keys = [key for key in labels if key in obj.counts] + [key for key in obj.counts if key not in labels]
        return "; ".join(f"{labels.get(key, key)}: {obj.counts[key]:,}" for key in keys)

    @admin.display(description="Output")
    def printed(self, obj):
        return format_html('<pre style="margin: 0; white-space: pre-wrap">{}</pre>', obj.output)

    def graphs_context(self, request, days):
        return job_graphs(days, job=request.GET.get("job", ""))
