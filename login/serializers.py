from rest_framework.serializers import ModelSerializer,Serializer
from  django.contrib.auth.models import User
from rest_framework import serializers

class UserSerializer(ModelSerializer):
    
    class Meta:
        model = User
        fields = ['username','password','first_name','last_name','email','is_staff']
        extra_kwargs = {'password':{'write_only':True}}
    def create(self, validated_data):
        
        user = User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password'],
            is_staff = validated_data.get('is_staff',False),
            last_name=validated_data['last_name'],
            first_name=validated_data['first_name'],
            email=validated_data['email'],
        )
        return user