from rest_framework import serializers

from .models import DockingJob, DockingResult, Pocket


class PocketSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pocket
        fields = [
            "id",
            "rank",
            "score",
            "probability",
            "center_x",
            "center_y",
            "center_z",
            "residue_ids",
            "sas_points",
            "composition",
        ]


class DockingResultSerializer(serializers.ModelSerializer):
    pocket_rank = serializers.IntegerField(source="pocket.rank", read_only=True)
    pocket_probability = serializers.FloatField(source="pocket.probability", read_only=True)
    center_x = serializers.FloatField(source="pocket.center_x", read_only=True)
    center_y = serializers.FloatField(source="pocket.center_y", read_only=True)
    center_z = serializers.FloatField(source="pocket.center_z", read_only=True)

    class Meta:
        model = DockingResult
        fields = [
            "id",
            "pocket_rank",
            "pocket_probability",
            "pose_rank",
            "affinity",
            "rmsd_lb",
            "rmsd_ub",
            "pose_file",
            "combined_score",
            "ligand_efficiency",
            "mmgbsa_score",
            "center_x",
            "center_y",
            "center_z",
        ]


class DockingJobStatusSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    num_results = serializers.SerializerMethodField()

    class Meta:
        model = DockingJob
        fields = [
            "id",
            "name",
            "status",
            "status_display",
            "num_pockets",
            "exhaustiveness",
            "scoring_function",
            "error_message",
            "num_results",
            "created_at",
            "updated_at",
        ]

    def get_num_results(self, obj):
        return DockingResult.objects.filter(pocket__job=obj).count()
