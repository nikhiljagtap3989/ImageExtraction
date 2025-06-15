from django.urls import path
from .views import LoginView, CreateUserAPIView,ProfileDetailsView,UserListView

urlpatterns = [
    path('IDA/login/', LoginView.as_view(), name='login'),
    # Add other URL patterns for different functionalities
    path('IDA/create_user/', CreateUserAPIView.as_view(), name='create_user'),
    path('profile/', ProfileDetailsView.as_view(), name='create_user'),
    path('users/', UserListView.as_view(), name='user-list'),
]