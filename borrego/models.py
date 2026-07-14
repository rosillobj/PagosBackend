from django.db import models
from django.contrib.auth.models import User
from pagos.models import Cliente


class Pendientes(models.Model):
    descripcion = models.CharField(max_length=250, null=True, blank=True)
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="pendientes",
    )
    status = models.BooleanField(default=True)  # True = abierto, False = cerrado
    closed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tickets_cerrados",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        cliente = self.idCliente.nombre if self.idCliente else "Sin cliente"
        print(cliente)
        return f"Ticket #{self.id} - {cliente}"