from rest_framework.exceptions import PermissionDenied
from rest_framework.serializers import ModelSerializer
from .models import Cliente, Pagos,antenasPerdidas,tokenExpo



class ClienteSerializer(ModelSerializer):
    def validate_frecuencia_pago(self, value):
        request = self.context.get("request")
        if request is None or request.user.pk != 1:
            raise PermissionDenied("Solo el usuario 1 puede cambiar la frecuencia de pago.")
        return value

    
    class Meta:
        model = Cliente
        fields = ['nombre','direccion','ip_completa','id','Tipo_instalacion','cortado','telefono','frecuencia_pago']

class PagosSerializer(ModelSerializer):
    
    class Meta:
        model = Pagos
        fields = ['id_cliente','january_p','january','february_p','february','march_p','march','april_p',
                  'april','may_p','may','june_p','june','july_p','july','august_p','august','september_p','september','october_p','october','november_p','november','december_p','december',
                  'ultimo_pago','ultimo_pago_p']

class AntenasPerdidasSerializer(ModelSerializer):
    
    class Meta:
        model = antenasPerdidas
        fields = ['nombre','direccion','telefono','ip','recuperable']

class TokenSerializer(ModelSerializer):
    model = tokenExpo
    fields = ['id_user','token']