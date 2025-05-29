from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate

from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from .serializers import LoginSerializer,UserSerializer,ProfileSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from rest_framework import generics

      

from django.contrib.auth.models import User   


class UserListView(generics.ListAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer


class CreateUserAPIView(APIView):
    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data['username']
            email = serializer.validated_data['email']
            password = serializer.validated_data['password']
            user = User.objects.create_user(username=username, email=email, password=password)
          
            token = get_tokens_for_user(user)
            
            
            return Response({'token': token, 'message': 'User created successfully'}, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        




#Generate token manually
def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)

    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }

class LoginView(APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data['username']
            password = serializer.validated_data['password']

            user = authenticate(request, username=username, password=password)

            #username="john", password="secret"
            #user = authenticate(request, email=email, password=password)
            if user is not None:
                # User authenticated

                refresh = RefreshToken.for_user(user)
         
                #token = get_tokens_for_user(user)
                #return Response({'token': token, 'username': username , 'message': 'Login successful'}, status=status.HTTP_200_OK)
                return Response({ 'refresh': str(refresh),'access': str(refresh.access_token) , 'username': username , 'message': 'Login successful'}, status=status.HTTP_200_OK)
            else:
                # Invalid credentials
                return Response({'message': 'Invalid email or password'}, status=status.HTTP_401_UNAUTHORIZED)
        else:
            # Invalid input data
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        

from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
class ProfileDetailsView(APIView):
    permission_class = [IsAuthenticated]
    def get(self,request):
        serializer = ProfileSerializer(request.user)
        
        return Response(serializer.data)
        



