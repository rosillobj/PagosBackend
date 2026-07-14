from rest_framework.serializers import ModelSerializer
from .models import Cliente, Pagos,antenasPerdidas,tokenExpo



class ClienteSerializer(ModelSerializer):
    
    class Meta:
        model = Cliente
        fields = ['nombre','direccion','ip_completa','id','Tipo_instalacion','cortado','telefono']

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