from django.shortcuts import render

# Create your views here.
from django.utils import timezone
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from .models import Pendientes
from .serializers import PendientesSerializer


class PendienteViewSet(ModelViewSet):
    queryset = Pendientes.objects.all().select_related("cliente", "closed_by")
    serializer_class = PendientesSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def get_queryset(self):
        qs = super().get_queryset().order_by("-created_at")

        status_param = self.request.query_params.get("status")
        cliente_id = self.request.query_params.get("cliente")

        if status_param is not None:
            if status_param.lower() in ["true", "1", "abierto"]:
                qs = qs.filter(status=True)
            elif status_param.lower() in ["false", "0", "cerrado"]:
                qs = qs.filter(status=False)

        if cliente_id:
            qs = qs.filter(cliente_id=cliente_id)

        return qs

    def perform_create(self, serializer):
        serializer.save()

    def perform_update(self, serializer):
        instance = self.get_object()
        new_status = serializer.validated_data.get("status", instance.status)

        # Si se cierra el ticket
        if instance.status is True and new_status is False:
            serializer.save(
                closed_by=self.request.user,
                closed_at=timezone.now(),
            )
        # Si se reabre el ticket
        elif instance.status is False and new_status is True:
            serializer.save(
                closed_by=None,
                closed_at=None,
            )
        else:
            serializer.save()