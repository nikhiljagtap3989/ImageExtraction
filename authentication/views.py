import logging
from django.contrib.auth import authenticate, get_user_model
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken

from authentication.models import CustomUser
from .serializers import LoginSerializer, UserSerializer, ProfileSerializer
from ImageExtraction.logger import log_exception  # Use actual project path


logger = logging.getLogger(__name__)


CustomUser = get_user_model()
class CreateUserAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        logger.info("User registration request received.")
        try:
            serializer = UserSerializer(data=request.data)

            if not serializer.is_valid():
                logger.warning("Invalid user data received during registration.")
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            email = serializer.validated_data['email']
            username = serializer.validated_data['username']

            # Check for duplicate email
            if CustomUser.objects.filter(email=email).exists():
                logger.warning(f"Email already registered: {email}")
                return Response({'message': 'Email already registered'}, status=status.HTTP_400_BAD_REQUEST)

            # Check for duplicate username
            if CustomUser.objects.filter(username=username).exists():
                logger.warning(f"Username already taken: {username}")
                return Response({'message': 'Username already taken'}, status=status.HTTP_400_BAD_REQUEST)

            password = serializer.validated_data['password']
            phone_number = serializer.validated_data['phone_number']

            # Create the user
            user = CustomUser.objects.create_user(username=username, email=email, password=password)
            user.phone_number = phone_number
            user.save()

            token = get_tokens_for_user(user)
            logger.info(f"User created successfully: {username} (Email: {email})")

            return Response({
                'token': token,
                'message': 'User created successfully'
            }, status=status.HTTP_201_CREATED)

        except Exception:
            logger.error("Error occurred during user registration.", exc_info=True)
            log_exception(logger)
            return Response(
                {"message": "An unexpected error occurred. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class UserListView(generics.ListAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer



#Generate token manually
def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)

    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
class ProfileDetailsView(APIView):
    permission_class = [IsAuthenticated]
    def get(self,request):
        serializer = ProfileSerializer(request.user)
        
        return Response(serializer.data)
        
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        logger.info("Login attempt received.")

        try:
            serializer = LoginSerializer(data=request.data)

            if not serializer.is_valid():
                logger.warning("Login failed: invalid data.")
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            username = serializer.validated_data['username']
            password = serializer.validated_data['password']

            user = authenticate(request, username=username, password=password)

            if user is not None:
                refresh = RefreshToken.for_user(user)

                logger.info(f"Login successful for user: {username}")
                return Response({
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                    'username': username,
                    'id': user.id,
                    'role': user.role,
                    'message': 'Login successful'
                }, status=status.HTTP_200_OK)
            else:
                logger.warning(f"Login failed for username: {username} — invalid credentials.")
                return Response({'message': 'Invalid email or password'}, status=status.HTTP_401_UNAUTHORIZED)

        except Exception:
            logger.error("Unexpected error occurred during login.", exc_info=True)
            log_exception(logger)
            return Response(
                {'message': 'An unexpected error occurred during login. Please try again later.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
