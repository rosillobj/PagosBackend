from django.db import models

# Create your models here.
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField
from django.utils import timezone
from django.contrib.auth.models import User

class Privada(models.Model):
    privada=models.CharField(max_length = 50, null = True,blank = True)
    def __str__(self):
        return self.privada
class Cliente(models.Model):
    privadas = [
    'abedul', 'abeto', 'abruzos','ahuehuete','alamo', 'alassia', 'alessandria','agrigento','aguaribay','amelia','ancona', 'aosta', 'arezo','basilicata','bari','barletta','bayan', 'belli','bolonia', 'brazalete','brindisi','bugato','bunya',
    'castaño','calabrece', 'catalpa','cedro','ciclamor', 'ciruelo', 'citrus','coliseo', 'daniel la pape', 'encina', 'eukalipto','farolillo', 'ferrara',
    'ferrari', 'flamboyan', 'florencia', 'haya', 'jacarandas', 'joaquin belli', 'kiri', 'latina','laurel',
    'liguria', 'majoleto', 'milan','nogal','paseos de la pradera','plaza libertad','plaza de la piedra', 'plaza del duomo','pavia','peral', 'perugia', 'plaza de la republica','puerta mayor',
    'plaza toscana alta', 'ravena', 'rio alia', 'rio enza', 'rio hada','roble','savona', 'secuoya', 'toscana media','venecia'
]

    privada = [(privada,privada)for privada in privadas]
    tipos = ["ubiquiti","mikrotik","cable"]
    tipo = [(tipo, tipo) for tipo in tipos] 
    rango = [(i, str(i)) for i in range(1, 20)]
    numero = [(i, str(i)) for i in range(1, 254)]
    cortado = models.BooleanField(default=False,null=True,blank=True)
    nombre = models.CharField(max_length=250,unique = True)
    direccion = models.CharField(max_length=250)
    Tipo_instalacion = models.CharField(max_length=70,null=True,choices=tipo)
    f_instalacion = models.DateField(auto_now_add=True)
    telefono = PhoneNumberField(blank=True, null=True)
    primera_parte_ip = models.PositiveSmallIntegerField(choices=rango)
    segunda_parte_ip = models.PositiveSmallIntegerField(choices=numero)
    ip_completa = models.CharField(max_length=15, unique=True)
    id_privada = models.ForeignKey(Privada,models.CASCADE,null=True,blank=True)
    recibo_pdf = models.FileField(null=True,blank=True)
    def __str__(self):
        return self.nombre
    def informacion_completa(self):
        return f"Nombre: {self.nombre}\nTeléfono: {self.telefono}\nDirección: {self.direccion}"
    class Meta:
        ordering =['nombre']

class Pagos(models.Model):
    Precio_Choices = [(i, "$" + str(i)) for i in range(200, 3050, 50)]
    
    id_user= models.ForeignKey(User, on_delete=models.DO_NOTHING,null=True)
    id_cliente = models.ForeignKey(Cliente, on_delete=models.DO_NOTHING,null=True,blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    january_p = models.IntegerField(null=True, blank=True)
    january = models.DateField(auto_now_add=False, null=True, blank=True)

    february_p = models.IntegerField(null=True, blank=True)
    february = models.DateField(auto_now_add=False, null=True, blank=True)

    march_p = models.IntegerField(null=True, blank=True)
    march = models.DateField(auto_now_add=False, null=True, blank=True)

    april_p = models.IntegerField(null=True, blank=True)
    april = models.DateField(auto_now_add=False, null=True, blank=True)

    may_p = models.IntegerField(null=True, blank=True)
    may = models.DateField(auto_now_add=False, null=True, blank=True)

    june_p = models.IntegerField(null=True, blank=True)
    june = models.DateField(auto_now_add=False, null=True, blank=True)

    july_p = models.IntegerField(null=True, blank=True)
    july = models.DateField(auto_now_add=False, null=True, blank=True)

    august_p = models.IntegerField(null=True, blank=True)
    august = models.DateField(auto_now_add=False, null=True, blank=True)

    september_p = models.IntegerField(null=True, blank=True)
    september = models.DateField(auto_now_add=False, null=True, blank=True)

    october_p = models.IntegerField(null=True, blank=True)
    october = models.DateField(auto_now_add=False, null=True, blank=True)

    november_p = models.IntegerField(null=True, blank=True)
    november = models.DateField(auto_now_add=False, null=True, blank=True)

    december_p = models.IntegerField(null=True, blank=True)
    december = models.DateField(auto_now_add=False, null=True, blank=True)


    ultimo_pago = models.DateField(auto_now=False,null=True,blank=True)
    ultimo_pago_p = models.IntegerField(null=True,blank=True)

    def __str__(self):
       return self.id_cliente
    
class antenasPerdidas(models.Model):
        
        
        nombre = models.CharField(max_length=200)
        inicial = models.CharField(max_length=200)
        final = models.CharField(max_length=400)
        ip = models.CharField(max_length=30)
        
class tokenExpo(models.Model):

    id_user = models.ForeignKey(User,on_delete=models.CASCADE,blank=True,null=True)
    token = models.CharField(max_length=100)
















