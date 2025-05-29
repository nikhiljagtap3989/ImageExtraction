from rest_framework import serializers
from django.contrib.auth.models import User

class LoginSerializer(serializers.ModelSerializer):
    #email = serializers.EmailField()
    username =  serializers.CharField()
    password = serializers.CharField()
    class Meta:
        model = User
        fields = ('username', 'password')


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['username', 'email', 'password']
        extra_kwargs = {'password': {'write_only': True}}


class ProfileSerializer(serializers.ModelSerializer):
   
    class Meta:
        model = User
        fields = ('id' ,'username', 'email')
