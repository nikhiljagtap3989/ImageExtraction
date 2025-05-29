from django.urls import path
from . import views
from django.conf.urls.static import static
from django.conf import settings

urlpatterns = [
    path("upload/", views.upload_and_process_file, name="upload_file"),
    path("details/", views.get_document_by_id, name="upload_file"),
    path('get-document/<int:doc_id>/', views.get_document_by_id, name='get_document_by_id')
]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

