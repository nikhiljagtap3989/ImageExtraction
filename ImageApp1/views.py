# views.py (using google-generativeai SDK for Gemini PDF extraction)

import os
import json
from dotenv import load_dotenv

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt

import google.generativeai as genai

from .models import Document

# Load environment variables and configure the Gemini API key
env_path = os.path.join(settings.BASE_DIR, '.env') if hasattr(settings, 'BASE_DIR') else None
if env_path and os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY not set in environment")
genai.configure(api_key=api_key)


from cryptography.fernet import Fernet
from django.conf import settings

def encrypt_id(id: int) -> str:
    fernet = Fernet(settings.FERNET_KEY)
    id_bytes = str(id).encode()  # convert int id to bytes
    encrypted = fernet.encrypt(id_bytes)
    return encrypted.decode()  # convert bytes back to string for JSON response

def decrypt_id(token: str) -> int:
    fernet = Fernet(settings.FERNET_KEY)
    decrypted = fernet.decrypt(token.encode())
    return int(decrypted.decode())

@csrf_exempt
def get_json_from_file(request):
    """
    Fetch previously generated JSON by filename.
    Expects a POST with raw JSON body: { "file_name": "example.json" }
    """
    if request.method != 'POST':
        return HttpResponseBadRequest("Only POST method is allowed")
    try:
        payload = json.loads(request.body)
        file_name = payload.get("file_name")
        if not file_name:
            return HttpResponseBadRequest("Missing 'file_name' in request")

        base_dir = os.path.join(settings.MEDIA_ROOT, "uploads/pdf_files")
        json_path = os.path.join(base_dir, file_name)
        if not os.path.exists(json_path):
            return JsonResponse({"error": "File not found"}, status=404)

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return JsonResponse(data, safe=False)

    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)




from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.http import JsonResponse
from django.conf import settings
from django.core.files.storage import default_storage
from django.shortcuts import get_object_or_404
from .models import Document

import os
import mimetypes
import json
from PIL import Image
from io import BytesIO

import google.generativeai as genai


# @csrf_exempt
class UploadAndProcessFileView(APIView):
    permission_classes = [IsAuthenticated]  # Require authentication token

    def post(self, request):
        uploaded_file = request.FILES.get("pdf_file")
        prompt_text = request.POST.get("prompt_text")
        user_id = request.POST.get("user_id")

        if not prompt_text:
            prompt_text = (
                "You are an intelligent data extraction model. Extract all relevant structured "
                "data from the invoice provided. Identify and capture any key information that "
                "would typically be found on a commercial invoice, such as metadata, party details, "
                "line items, totals, and any other meaningful elements. Present the extracted data "
                "in a well-organized HTML format."
            )

        if not uploaded_file:
            return Response({"status": "error", "message": "Missing 'pdf_file'"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Ensure upload directory exists
            custom_dir = "uploads/pdf_files"
            save_dir = os.path.join(settings.MEDIA_ROOT, custom_dir)
            os.makedirs(save_dir, exist_ok=True)

            file_name = uploaded_file.name
            extension = os.path.splitext(file_name)[1].lower()

            relative_path = default_storage.save(os.path.join(custom_dir, file_name), uploaded_file)
            absolute_path = os.path.join(settings.MEDIA_ROOT, relative_path)

            mime_type, _ = mimetypes.guess_type(absolute_path)

            if extension in [".jpg", ".jpeg", ".png"]:
                image = Image.open(absolute_path)
                buffer = BytesIO()
                image.save(buffer, format=image.format)
                image_bytes = buffer.getvalue()
                mime_type = f"image/{image.format.lower()}"
                data_part = {"mime_type": mime_type, "data": image_bytes}

            elif extension == ".pdf":
                with open(absolute_path, "rb") as f:
                    pdf_bytes = f.read()
                data_part = {"mime_type": "application/pdf", "data": pdf_bytes}

            else:
                return Response({"status": "error", "message": "Unsupported file type"}, status=status.HTTP_400_BAD_REQUEST)

            # Gemini model processing
            generation_config = {"response_mime_type": "application/json"}
            model = genai.GenerativeModel("gemini-2.0-flash", generation_config=generation_config)
            response = model.generate_content([data_part, prompt_text])
            parsed_json = json.loads(response.text)

            # Save JSON to file
            json_filename = os.path.splitext(relative_path)[0] + ".json"
            json_path = os.path.join(settings.MEDIA_ROOT, json_filename)
            with open(json_path, "w", encoding="utf-8") as jf:
                json.dump(parsed_json, jf, indent=2)

            # Save to DB
            doc = Document.objects.create(
                filepath=relative_path,
                file=relative_path,
                json_data=parsed_json,
                userid_id = user_id
            )


            encrypted_doc_id = encrypt_id(doc.id)

            return Response({"status": "success", "document_id": encrypted_doc_id}, status=status.HTTP_200_OK)

            # return Response({"status": "success", "document_id": doc.id}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .models import Document  # your Document model
from django.shortcuts import get_object_or_404



from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404


class GetDocumentByIdView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id):
        try:
            decrypted_id = decrypt_id(doc_id)
            doc = get_object_or_404(Document, id=decrypted_id)
            return Response({
                "status": "success",
                "filepath": request.build_absolute_uri(doc.file.url),
                "json_data": doc.json_data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": "Invalid or corrupted document ID"}, status=status.HTTP_400_BAD_REQUEST)


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .models import Document
from .serializers import DocumentSerializer


# class UserDocumentView(APIView):
#     permission_classes = [IsAuthenticated]

#     def get(self, request):
#         user = request.user

#         if user.id == 2:
#             documents = Document.objects.all()
#         else:
#             documents = Document.objects.filter(userid=user)

#         serializer = DocumentSerializer(documents, many=True)


#         return Response({
#             "count": documents.count(),  # ✅ total count
#             "documents": serializer.data
#         }, status=status.HTTP_200_OK)
#         # return Response(serializer.data, status=status.HTTP_200_OK)

class UserDocumentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if user.id == 2:
            documents = Document.objects.all()
        else:
            documents = Document.objects.filter(userid=user)

        serializer = DocumentSerializer(documents, many=True)
        serialized_data = serializer.data

        # Encrypt the 'id' field
        for doc in serialized_data:
            doc['id'] = encrypt_id(doc['id'])

        return Response({
            "count": documents.count(),
            "documents": serialized_data
        }, status=status.HTTP_200_OK)



from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Document
from .serializers import DocumentSerializer
from django.utils.dateparse import parse_date

class FilteredDocumentView(APIView):
    def post(self, request):
        user_id = request.data.get('userid')
        date_str = request.data.get('date')

        if not user_id or not date_str:
            return Response({
                "error": "Both 'userid' and 'date' fields are required in the request body."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            entry_date = parse_date(date_str)
            if not entry_date:
                return Response({
                    "error": "Invalid date format. Please use YYYY-MM-DD."
                }, status=status.HTTP_400_BAD_REQUEST)

            documents = Document.objects.filter(userid=user_id, entry_date=entry_date)
            serializer = DocumentSerializer(documents, many=True)

           


            return Response({
                "count": documents.count(),
                "documents": serializer.data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

from django.views import View
from django.shortcuts import render
from cryptography.fernet import InvalidToken

JSON_TO_HTML_PROMPT = """
You are an expert at converting structured JSON data into well-formatted, human-readable HTML.
Given the following JSON data, create a clean and semantic HTML representation of the invoice information.
Focus on readability and clear presentation. Use appropriate HTML tags (e.g., <h1>, <h2>, <table>, <ul>, <p>, <span>, <div>) to structure the data.
If there are line items, present them in a table. Ensure all key details like invoice number, dates, totals, sender, recipient, and line items are clearly visible.
DO NOT include any CSS or JavaScript. Just pure HTML.

JSON Data:
{}
"""

class RenderJsonToHtmlView(View):
    def get(self, request, encrypted_id):
        try:
            decrypted_id = decrypt_id(encrypted_id)
        except InvalidToken:
            return JsonResponse({"error": "Invalid ID"}, status=400)

        doc = get_object_or_404(Document, id=decrypted_id)
        json_data = doc.json_data

        # Use Gemini to convert JSON to HTML
        prompt = JSON_TO_HTML_PROMPT.format(json.dumps(json_data, indent=2))
        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content(prompt)
        html_body = response.text  # This is pure HTML content

        return render(request, 'rendered_html.html', {'html_body': html_body})
