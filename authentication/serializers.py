from rest_framework import serializers
from django.contrib.auth.models import User

from .models import CustomUser


class LoginSerializer(serializers.ModelSerializer):
    #email = serializers.EmailField()
    username =  serializers.CharField()
    password = serializers.CharField()
    class Meta:
        model = CustomUser
        fields = ('username', 'password')


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'password','phone_number']
        extra_kwargs = {'password': {'write_only': True}}


class ProfileSerializer(serializers.ModelSerializer):
   
    class Meta:
        model = CustomUser
        fields = ('id' ,'username', 'email')
