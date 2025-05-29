from django.shortcuts import render


import os
import json
from dotenv import load_dotenv
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse

from . import prompt  # Make sure this contains `Application_Form`
from django.core.files.storage import default_storage




from django.http import JsonResponse
from django.core.files.storage import default_storage
from django.conf import settings
import os, json
from .models import Document  # ✅ Import your model



from django.conf import settings  # Needed for MEDIA_ROOT
import os
import json
from dotenv import load_dotenv
# from google import genai
# from google.genai import types
from  . import prompt  # Make sure this contains `Extraction_Prompt`

import google.generativeai as genai

# Load environment variables from .env
load_dotenv()

# Fetch API key from environment
api_key = os.getenv("GEMINI_API_KEY")

# Initialize Gemini client
# client = genai.Client(api_key=api_key)

client = genai.configure(api_key=api_key)
print(api_key)

# def upload_and_process_file(request):
#     if request.method == "POST" and request.FILES.get("pdf_file") and request.POST.get("prompt_text"):
#         uploaded_file = request.FILES["pdf_file"]
#         prompt_text = request.POST["prompt_text"]
#         # custom_dir = "uploads/pdf_files/"  # Relative path from MEDIA_ROOT
#         # file_name = uploaded_file.name
#         # file_path = default_storage.save(os.path.join(custom_dir, file_name), uploaded_file)

#         # # file_path = default_storage.save(uploaded_file.name, uploaded_file)

#         # try:
#         #     # Upload file to Gemini
#         #     uploaded_gemini_file = client.files.upload(file=file_path)
        
#         custom_dir = "uploads/pdf_files/"
#         file_name = uploaded_file.name
#         file_path = default_storage.save(os.path.join(custom_dir, file_name), uploaded_file)

#         try:
#             # Get absolute path for Gemini upload
#             absolute_file_path = os.path.join(settings.MEDIA_ROOT, file_path)
#             uploaded_gemini_file = client.files.upload(file=absolute_file_path)


#             # Generate content (requesting JSON format)
#             response = client.models.generate_content(
#                 model="gemini-2.0-flash",
#                 config={'response_mime_type': 'application/json'},
#                 contents=[uploaded_gemini_file, 
#                         #   prompt.Application_Form
#                         prompt_text
#                           ],
#             )

#             # Check response content
#             raw_text = response.text
#             print("🔍 Raw Gemini response:\n", raw_text)

#             try:
#                 parsed_json = json.loads(raw_text)
#             except json.JSONDecodeError as json_err:
#                 return JsonResponse({
#                     "status": "error",
#                     "message": f"❌ JSON parse error: {json_err}",
#                     "raw_response": raw_text[:500] + "..."  # truncate to avoid very long output
#                 })

#             # Optional: Save response to file
#             output_path = os.path.splitext(file_path)[0] + ".json"
#             with open(output_path, "w", encoding="utf-8") as f:
#                 json.dump(parsed_json, f, indent=2)

#             return JsonResponse({"status": "success", "response": parsed_json})

#         except Exception as e:
#             return JsonResponse({"status": "error", "message": str(e)})



# views.py
import os
import json
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

@csrf_exempt
def get_json_from_file(request):
    if request.method == 'POST':
        try:
            body = json.loads(request.body)
            file_name = body.get("file_name")

            if not file_name:
                return HttpResponseBadRequest("Missing 'file_name' in request")

            custom_dir = "uploads/pdf_files/"
            # Path to JSON file
            # json_path = os.path.join(settings.BASE_DIR, "json_files", file_name)
            json_path = os.path.join(custom_dir, file_name)

            if not os.path.exists(json_path):
                return JsonResponse({"error": "File not found"}, status=404)

            with open(json_path, "r") as f:
                data = json.load(f)

            return JsonResponse(data)

        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid JSON")
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return HttpResponseBadRequest("Only POST method is allowed")


from django.views.decorators.csrf import csrf_exempt

import os
import json
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.core.files.storage import default_storage
from django.conf import settings
from .models import Document
import traceback

@csrf_exempt  
def upload_and_process_file(request):
    print("📥 Request:", request)
    print("📄 Method:", request.method)
    print("📁 Files:", request.FILES)
    
    if request.method == "POST":
        uploaded_file = request.FILES.get("pdf_file")
        prompt_text = request.POST.get("prompt_text")
        print(prompt_text)
        if not uploaded_file or not prompt_text:
            return JsonResponse({"status": "error", "message": "Missing 'pdf_file' or 'prompt_text'"}, status=400)

        try:
            custom_dir = "uploads/pdf_files/"
            os.makedirs(os.path.join(settings.MEDIA_ROOT, custom_dir), exist_ok=True)

            file_name = uploaded_file.name
            file_path = default_storage.save(os.path.join(custom_dir, file_name), uploaded_file)

            # image_path = r"D:/test/Test_Invoice.pdf"

            print(file_path)
            absolute_file_path = os.path.join(settings.MEDIA_ROOT, file_path)            
            uploaded_gemini_file = client.files.upload(file=image_path)                  

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                config={'response_mime_type': 'application/json'},
                contents=[uploaded_gemini_file, prompt_text],
            )
        
            raw_text = response.text
            print("🔍 Raw Gemini response:\n", raw_text[:500])  # Print partial for debugging

            try:
                parsed_json = json.loads(raw_text)
            except json.JSONDecodeError as json_err:
                return JsonResponse({
                    "status": "error",
                    "message": f"❌ JSON parse error: {json_err}",
                    "raw_response": raw_text[:500] + "..."
                })

            # Save parsed JSON to a file
            output_path = os.path.splitext(file_path)[0] + ".json"
            with open(os.path.join(settings.MEDIA_ROOT, output_path), "w", encoding="utf-8") as f:
                json.dump(parsed_json, f, indent=2)

            # Save to database
            doc = Document.objects.create(
                filepath=file_path,
                file=file_path,
                json_data=parsed_json
            )

            return JsonResponse({"status": "success", "document_id": doc.id})

        except Exception as e:
            print(traceback.print_exc())
            return JsonResponse({"status": "error", "message": str(e)}, status=500)

    return JsonResponse({"status": "error", "message": "Invalid request method"}, status=405)
