from django.shortcuts import render
from .serializers import UserSerializer
from rest_framework.generics import ListCreateAPIView, DestroyAPIView,CreateAPIView,ListAPIView,UpdateAPIView
from rest_framework.permissions import AllowAny,IsAuthenticated
from django.contrib.auth.models import User
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView


class UserRegister(CreateAPIView):
    
    serializer_class = UserSerializer
    queryset = User.objects.all()
    permission_classes = [AllowAny]
    
    def create(self, request, *args, **kwargs):
        
        serializer = self.get_serializer(data=request.data)
        print(request.data)
        if serializer.is_valid():
            print("Se REgistro el Usuario")
        else:
            print("Errores",serializer.errors)
            return Response({'status': 'error',
                             'errors':serializer.errors},status=status.HTTP_400_BAD_REQUEST)
        return super().create(request, *args, **kwargs)