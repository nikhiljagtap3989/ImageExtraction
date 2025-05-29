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

# @csrf_exempt
# def upload_and_process_file(request):
#     """
#     Handles a multipart POST with:
#       - pdf_file (File)
#       - prompt_text (Text)

#     Saves the PDF, invokes Gemini extraction,
#     persists the JSON side-by-side and into the Document model.
#     """
#     if request.method != "POST":
#         return JsonResponse({"status": "error", "message": "Invalid request method"}, status=405)

#     uploaded_file = request.FILES.get("pdf_file")
#     prompt_text = request.POST.get("prompt_text")
#     if not uploaded_file or not prompt_text:
#         return JsonResponse({"status": "error", "message": "Missing 'pdf_file' or 'prompt_text'"}, status=400)

#     try:
#         # Ensure upload directory exists
#         custom_dir = "uploads/pdf_files"
#         save_dir = os.path.join(settings.MEDIA_ROOT, custom_dir)
#         os.makedirs(save_dir, exist_ok=True)

#         # Save PDF to MEDIA_ROOT
#         file_name = uploaded_file.name
#         relative_path = default_storage.save(os.path.join(custom_dir, file_name), uploaded_file)
#         absolute_path = os.path.join(settings.MEDIA_ROOT, relative_path)

#         # Read PDF bytes
#         with open(absolute_path, "rb") as f:
#             pdf_bytes = f.read()
#         pdf_part = {"mime_type": "application/pdf", "data": pdf_bytes}

#         # Prepare model with JSON output
#         generation_config = {"response_mime_type": "application/json"}
#         model = genai.GenerativeModel("gemini-2.0-flash", generation_config=generation_config)

#         # Call generate_content as positional
#         response = model.generate_content([pdf_part, prompt_text])

#         # Parse and save JSON
#         parsed_json = json.loads(response.text)
#         json_filename = os.path.splitext(relative_path)[0] + ".json"
#         json_path = os.path.join(settings.MEDIA_ROOT, json_filename)
#         with open(json_path, "w", encoding="utf-8") as jf:
#             json.dump(parsed_json, jf, indent=2)

#         # Persist record
#         doc = Document.objects.create(
#             filepath=relative_path,
#             file=relative_path,
#             json_data=parsed_json,
#         )

#         return JsonResponse({"status": "success", "document_id": doc.id})

#     except Exception as e:
#         return JsonResponse({"status": "error", "message": str(e)}, status=500)

from PIL import Image
from io import BytesIO
import mimetypes
@csrf_exempt
def upload_and_process_file(request):
    """
    Handles a multipart POST with:
      - pdf_file (File)
      - prompt_text (Text)

    Saves the PDF, invokes Gemini extraction,
    persists the JSON side-by-side and into the Document model.
    """
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid request method"}, status=405)

    uploaded_file = request.FILES.get("pdf_file")
    prompt_text = request.POST.get("prompt_text")

    if not prompt_text:
        prompt_text="You are an intelligent data extraction model. Extract all relevant structured data from the invoice provided.Identify and capture any key information that would typically be found on a commercial invoice, such as metadata, party details,line items, totals, and any other meaningful elements. Present the extracted data in a well-organized HTML format."

    if not uploaded_file or not prompt_text:
        return JsonResponse({"status": "error", "message": "Missing 'pdf_file' or 'prompt_text'"}, status=400)

    try:
        # Ensure upload directory exists
        custom_dir = "uploads/pdf_files"
        save_dir = os.path.join(settings.MEDIA_ROOT, custom_dir)
        os.makedirs(save_dir, exist_ok=True)

        # Save PDF to MEDIA_ROOT
        file_name = uploaded_file.name

       
        extension = os.path.splitext(file_name)[1].lower()

        relative_path = default_storage.save(os.path.join(custom_dir, file_name), uploaded_file)
        absolute_path = os.path.join(settings.MEDIA_ROOT, relative_path)

        mime_type, _ = mimetypes.guess_type(absolute_path)

        if extension in [".jpg", ".jpeg", ".png"]:
            # Convert image to bytes
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
            return JsonResponse({"status": "error", "message": "Unsupported file type"}, status=400)


        # Prepare model with JSON output
        generation_config = {"response_mime_type": "application/json"}
        model = genai.GenerativeModel("gemini-2.0-flash", generation_config=generation_config)

        # Call generate_content as positional
        response = model.generate_content([data_part, prompt_text])

        # Parse and save JSON
        parsed_json = json.loads(response.text)
        json_filename = os.path.splitext(relative_path)[0] + ".json"
        json_path = os.path.join(settings.MEDIA_ROOT, json_filename)
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(parsed_json, jf, indent=2)

        # Persist record
        doc = Document.objects.create(
            filepath=relative_path,
            file=relative_path,
            json_data=parsed_json,
        )

        return JsonResponse({"status": "success", "document_id": doc.id})

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


# views.py
from django.http import JsonResponse
from .models import Document


def get_document_by_id(request, doc_id):
    try:
        doc = Document.objects.get(id=doc_id)
        return JsonResponse({
            "status": "success",
            "filepath": request.build_absolute_uri(doc.file.url),       # Returns media URL if MEDIA_URL is configured
            "json_data": doc.json_data
        })
    except Document.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": f"Document with id {doc_id} not found."
        }, status=404)