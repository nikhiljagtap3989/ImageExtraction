from django.urls import path
from . import views
from django.conf.urls.static import static
from django.conf import settings


from django.urls import path
from .views import GetDocumentByIdView ,UserDocumentView,FilteredDocumentView # <-- This line is important
from .views import RenderJsonToHtmlView

urlpatterns = [
    # path("upload/", views.upload_and_process_file, name="upload_file"),
    # path("details/", views.get_document_by_id, name="upload_file"),
    # path('get-document/<int:doc_id>/', views.get_document_by_id, name='get_document_by_id')
    path("upload/", views.UploadAndProcessFileView.as_view(), name="upload_file"),
    # path('get-document/<int:doc_id>/', views.GetDocumentByIdView.as_view(), name='get-document-by-id'),
    path('documents/', UserDocumentView.as_view(), name='user-documents'),
    path('document-filter/', FilteredDocumentView.as_view(), name='filtered-documents'),
    path('get-document/<path:doc_id>/', GetDocumentByIdView.as_view(), name='get-document-by-id'),  # Note: <path:doc_id>
    path('render-html/<path:encrypted_id>/', RenderJsonToHtmlView.as_view(), name='render_html'),
]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)