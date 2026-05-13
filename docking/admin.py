from django.contrib import admin

from .models import DockingJob, Pocket, DockingResult


@admin.register(DockingJob)
class DockingJobAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "status", "num_pockets", "created_at")
    list_filter = ("status",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Pocket)
class PocketAdmin(admin.ModelAdmin):
    list_display = ("id", "job", "rank", "probability", "center_x", "center_y", "center_z")
    list_filter = ("job",)


@admin.register(DockingResult)
class DockingResultAdmin(admin.ModelAdmin):
    list_display = ("id", "pocket", "pose_rank", "affinity", "combined_score")
    list_filter = ("pocket__job",)
