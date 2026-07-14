from rest_framework.serializers import ModelSerializer
from .models import Pendientes


class PendientesSerializer(ModelSerializer):
    class Meta:
        model = Pendientes
        fields = [
            "id",
            "descripcion",
            "cliente",
            "status",
            "created_at",
            "closed_at",
            "closed_by",
        ]
        read_only_fields = ["id", "created_at", "closed_at", "closed_by"]