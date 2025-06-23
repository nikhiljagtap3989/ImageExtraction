from django.urls import path
from . import views
from django.conf.urls.static import static
from django.conf import settings


from django.urls import path
from .views import GetDocumentByIdView ,UserDocumentView,FilteredDocumentView # <-- This line is important
from .views import RenderJsonToHtmlView , UploadAndValidateReimbursementView,UploadAndProcessFileView
urlpatterns = [
    path("upload/", UploadAndProcessFileView.as_view(), name="upload_file"),
    # path("upload_receipt/", UploadAndProcessReceiptView.as_view(), name="upload_file"),
    path('documents/', UserDocumentView.as_view(), name='user-documents'),
    path('document-filter/', FilteredDocumentView.as_view(), name='filtered-documents'),
    path('get-document/<path:doc_id>/', GetDocumentByIdView.as_view(), name='get-document-by-id'),  # Note: <path:doc_id>
    path('render-html/', RenderJsonToHtmlView.as_view(), name='render_html'),
    
    path('reimbursement-upload/', UploadAndValidateReimbursementView.as_view(), name='reimbursement-upload'),
]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)



