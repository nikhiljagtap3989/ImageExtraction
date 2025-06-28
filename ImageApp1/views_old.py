import os
import json
from dotenv import load_dotenv
from django.conf import settings
from django.core.files.storage import default_storage
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
import google.generativeai as genai
from django.views import View

from .models import Document
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.shortcuts import get_object_or_404,render

import mimetypes
from PIL import Image
from io import BytesIO

from .serializers import DocumentSerializer
from django.utils import timezone
from cryptography.fernet import InvalidToken

from django.utils.dateparse import parse_date
from cryptography.fernet import Fernet
from django.conf import settings

import logging
from ImageExtraction.logger import log_exception 

# Setup logger
logger = logging.getLogger(__name__)

from .vertex_model import call_gemini_api


# Load environment variables and configure the Gemini API key
env_path = os.path.join(settings.BASE_DIR, '.env') if hasattr(settings, 'BASE_DIR') else None
if env_path and os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

import json

def safe_json_load(raw_string: str):
    if not raw_string or not raw_string.strip():
        raise json.JSONDecodeError("Empty or whitespace-only string", raw_string, 0)

    cleaned = raw_string.strip()

    if cleaned.startswith("```json"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1])

    return json.loads(cleaned)



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

class GetDocumentByIdView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, doc_id):
        try:
            logger.info(f"GetDocumentByIdView called with encrypted ID: {doc_id}")

            # 1) Decrypt
            decrypted_id = decrypt_id(doc_id)
            logger.debug(f"Decrypted ID: {decrypted_id}")

            # 2) Fetch object or 404
            doc = get_object_or_404(Document, id=decrypted_id)
            logger.info(f"Document {decrypted_id} retrieved successfully")

            # 3) Build absolute URL for file download
            file_url = request.build_absolute_uri(doc.file.url)

            return Response({
                "status": "success",
                "filepath": file_url,
                "json_data": doc.json_data,
                "html_data": doc.html_content,
                "input_token": doc.input_token,
                "output_token":doc.output_token
            }, status=status.HTTP_200_OK)

        except Exception:
            logger.error("Error while fetching document by ID", exc_info=True)
            log_exception(logger)          # ⬅️  full traceback to file
            return Response(
                {"error": "Invalid or corrupted document ID"},
                status=status.HTTP_400_BAD_REQUEST
            )

class UserDocumentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            logger.info(f"UserDocumentView accessed by user ID: {user.id}")

            if user.id == 2:
                documents = Document.objects.all()
                logger.info("Admin user detected: Fetching all documents.")
            else:
                documents = Document.objects.filter(userid=user)
                logger.info(f"Fetching documents for user ID: {user.id}")

            serializer = DocumentSerializer(documents, many=True)
            serialized_data = serializer.data
            logger.info(f"{len(serialized_data)} documents retrieved successfully.")

            # Encrypt the 'id' field
            for doc in serialized_data:
                doc['id'] = encrypt_id(doc['id'])


            total_input_tokens = sum(getattr(doc, "input_token", 0) or 0 for doc in documents)
            total_output_tokens = sum(getattr(doc, "output_token", 0) or 0 for doc in documents)

            logger.info(f"{len(serialized_data)} documents retrieved. Total input: {total_input_tokens}, output: {total_output_tokens}")

            

            return Response({
                "count": documents.count(),
                "documents": serialized_data,
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,

            }, status=status.HTTP_200_OK)
            

        except Exception:
            logger.error("Exception occurred while fetching user documents.", exc_info=True)
            log_exception(logger)
            return Response({
                "status": "error",
                "message": "An error occurred while retrieving documents. Please try again later."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class FilteredDocumentView(APIView):
    def post(self, request):
        try:
            user_id = request.data.get('userid')
            date_str = request.data.get('date')

            logger.info(f"FilteredDocumentView called with user_id={user_id} and date={date_str}")

            if not user_id or not date_str:
                logger.warning("Missing 'userid' or 'date' in request body.")
                return Response({
                    "error": "Both 'userid' and 'date' fields are required in the request body."
                }, status=status.HTTP_400_BAD_REQUEST)

            entry_date = parse_date(date_str)
            if not entry_date:
                logger.warning(f"Invalid date format received: {date_str}")
                return Response({
                    "error": "Invalid date format. Please use YYYY-MM-DD."
                }, status=status.HTTP_400_BAD_REQUEST)

            documents = Document.objects.filter(userid=user_id, entry_date=entry_date)
            serializer = DocumentSerializer(documents, many=True)

            logger.info(f"{documents.count()} documents found for user_id={user_id} on {entry_date}")

            return Response({
                "count": documents.count(),
                "documents": serializer.data
            }, status=status.HTTP_200_OK)

        except Exception:
            logger.error("Exception occurred while filtering documents.", exc_info=True)
            log_exception(logger)
            return Response({
                "error": "An internal error occurred. Please try again later."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class RenderJsonToHtmlView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        encrypted_id = data.get("encrypted_doc_id")
        user_id = data.get("userid")

        if not encrypted_id or not user_id:
            return JsonResponse({"error": "Missing required fields"}, status=400)

        try:
            decrypted_id = decrypt_id(encrypted_id)
        except InvalidToken:
            return JsonResponse({"error": "Invalid encrypted ID"}, status=400)

        doc = get_object_or_404(Document, id=decrypted_id, userid_id=user_id)
        json_data = doc.json_data

        JSON_TO_HTML_PROMPT = """ 
            You are an expert at converting structured JSON data into a complete, human-readable, and printable HTML document. 

            Your task is to generate a **fully styled and structured HTML report** using the provided JSON data. 

            Requirements: 
            1. Wrap the entire content in `<!DOCTYPE html>`, `<html>`, `<head>`, and `<body>` tags. 
            2. Inside the `<head>`: 
            - Add a `<meta charset="UTF-8">` tag. 
            - Set a proper `<title>` based on the document type (e.g., "Invoice Report", "Document Analysis"). 
            - Include a `<style>` tag with CSS for layout, table formatting, and conditional formatting. 
            3. Inside the `<body>`: 
            - Use a centered `.container` div with padding, background, shadow, and max-width. 
            - Display document title and relevant header information. 
            - Show key information in structured format using `<p>`, `<h3>`, etc. 
            - Use `<table>` for tabular data with proper headers and styling. 
            - Apply appropriate CSS classes for different data types. 
            - Add professional styling with proper spacing and typography. 

            STRICT RULES: 
            - Do NOT include JavaScript or external CSS. 
            - Use only embedded CSS inside a `<style>` tag. 
            - Do NOT include forms, inputs, buttons, links, or scripts. 
            - Do NOT use markdown code blocks or ```html formatting in your response.
            - Return only the raw HTML code without any explanations, comments, or formatting.

            OUTPUT FORMAT: 
            Your response must start with:
            <!DOCTYPE html>

            And must end with:
            </html>

            Do not include any text before <!DOCTYPE html> or after </html>
            Do not wrap the HTML in markdown code blocks or any other formatting

            JSON Data: 
            {} 
            """.strip()

        prompt = JSON_TO_HTML_PROMPT.format(json.dumps(json_data, indent=2))

        response = call_gemini_api(
            prompt_text=prompt
        )
        result = response['candidates'][0]['content']['parts'][0]['text']
        raw_html = result

    

        # 🔧 Handle if the model returns a list or extra escaping
        try:
            # if response is a list as a string
            parsed_html = json.loads(raw_html)
            if isinstance(parsed_html, list):
                html_body = "".join(parsed_html)  # merge all parts
            else:
                html_body = parsed_html
        except Exception:
            html_body = raw_html

        # Final cleanup
        html_body = html_body.replace("\\n", "").replace("\n", "").replace('\\"', '"')

        return render(request, 'rendered_html.html', {'html_body': html_body})


class UploadAndProcessFileView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        uploaded_file = request.FILES.get("pdf_file")
        prompt_text = request.POST.get("prompt_text")
        user_id = request.POST.get("user_id")
        doc_type =  request.POST.get("doc_type")

        logger.info("Upload request received")

        input_tokens=""
        output_tokens=""

        if not uploaded_file:
            logger.error("Upload failed: 'File' is missing in the request.", exc_info=True)
         
            return Response(
                {"status": "error", "message": "Missing 'pdf_file'"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not prompt_text:
            prompt_text = (
                "You are an intelligent data extraction model. Extract all relevant structured "
                "data from the invoice provided. Identify and capture any key information that "
                "would typically be found on a commercial invoice, such as metadata, party details, "
                "line items, totals, and any other meaningful elements. Present the extracted data "
                "in a structured JSON format."
                "dont add ```json or ``` in your response"
            )

        try:
            # Save uploaded file
            custom_dir = "uploads/pdf_files"
            save_dir = os.path.join(settings.MEDIA_ROOT, custom_dir)
            os.makedirs(save_dir, exist_ok=True)

            file_name = uploaded_file.name
            extension = os.path.splitext(file_name)[1].lower()
            relative_path = default_storage.save(os.path.join(custom_dir, file_name), uploaded_file)
            absolute_path = os.path.join(settings.MEDIA_ROOT, relative_path)

            # Prepare file for Gemini
            if extension in [".jpg", ".jpeg", ".png"]:
                image = Image.open(absolute_path)
                buffer = BytesIO()
                image.save(buffer, format=image.format)
                data_part = {"mime_type": f"image/{image.format.lower()}", "data": buffer.getvalue()}
            elif extension == ".pdf":
                with open(absolute_path, "rb") as f:
                    data_part = {"mime_type": "application/pdf", "data": f.read()}
            else:
                logger.error("Unsupported file type", exc_info=True)
                return Response(
                    {"status": "error", "message": "Unsupported file type"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            JSON_TO_HTML_PROMPT = """ 
            You are an expert at converting structured JSON data into a complete, human-readable, and printable HTML document. 

            Your task is to generate a **fully styled and structured HTML report** using the provided JSON data. 

            Requirements: 
            1. Wrap the entire content in `<!DOCTYPE html>`, `<html>`, `<head>`, and `<body>` tags. 
            2. Inside the `<head>`: 
            - Add a `<meta charset="UTF-8">` tag. 
            - Set a proper `<title>` based on the document type (e.g., "Invoice Report", "Document Analysis"). 
            - Include a `<style>` tag with CSS for layout, table formatting, and conditional formatting. 
            3. Inside the `<body>`: 
            - Use a centered `.container` div with padding, background, shadow, and max-width. 
            - Display document title and relevant header information. 
            - Show key information in structured format using `<p>`, `<h3>`, etc. 
            - Use `<table>` for tabular data with proper headers and styling. 
            - Apply appropriate CSS classes for different data types. 
            - Add professional styling with proper spacing and typography. 

            STRICT RULES: 
            - Do NOT include JavaScript or external CSS. 
            - Use only embedded CSS inside a `<style>` tag. 
            - Do NOT include forms, inputs, buttons, links, or scripts. 
            - Do NOT use markdown code blocks or ```html formatting in your response.
            - Return only the raw HTML code without any explanations, comments, or formatting.

            OUTPUT FORMAT: 
            Your response must start with:
            <!DOCTYPE html>

            And must end with:
            </html>

            Do not include any text before <!DOCTYPE html> or after </html>
            Do not wrap the HTML in markdown code blocks or any other formatting

            JSON Data: 
            {} 
            """.strip()

            if doc_type == 'docextraction':    

                
                   
                # Step 1: Extract structured JSON
                # model = genai.GenerativeModel("gemini-2.0-flash", generation_config={"response_mime_type": "application/json"})
                # # model = GenerativeModel(model_name="models/gemini-1.5-flash", generation_config={"response_mime_type": "application/json"})
                # response = model.generate_content([data_part, prompt_text])
                try:
                    response = call_gemini_api(
                        prompt_text=prompt_text,
                        input_data=absolute_path,
                        response_mime_type="application/json"
                    )
                    
                    if not response or 'candidates' not in response:
                        logger.error("Invalid API response format", exc_info=True)
                        return Response({"error": "Invalid API response format"}, status=500)
                    
                    result = response['candidates'][0]['content']['parts'][0]['text']
                    print("API response:", result)
                    
                    if not result:
                        logger.error("Empty response from API", exc_info=True)
                        return Response({"error": "Empty response from API"}, status=500)
                    
                    parsed_json = safe_json_load(result)
                    
                    if not isinstance(parsed_json, dict):
                        logger.error("Parsed JSON is not a dictionary", exc_info=True)
                        return Response({"error": "Invalid JSON format"}, status=400)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decoding error: {str(e)}", exc_info=True)
                    return Response({"error": "Invalid JSON received from API"}, status=400)
                except Exception as e:
                    logger.error(f"Error processing API response: {str(e)}", exc_info=True)
                    return Response({"error": str(e)}, status=500)
                if parsed_json is None:
                    logger.error("Invalid JSON received. Cannot parse JSON.", exc_info=True)
                    return Response({"error": "Invalid JSON received"}, status=400)

                if 'usageMetadata' in response:
                    usage_metadata = response['usageMetadata']
                    input_tokens = usage_metadata.get('promptTokenCount', 0)
                    output_tokens = usage_metadata.get('candidatesTokenCount', 0)
                    total_tokens = usage_metadata.get('totalTokenCount', 0)

                    logger.info(f"Input Tokens: {input_tokens}")
                    logger.info(f"Output Tokens: {output_tokens}")
                    logger.info(f"Total Tokens: {total_tokens}")
                else:
                    logger.info("Usage metadata not available in the response.")

                if not input_tokens:
                    logger.error("Input tokens is empty", exc_info=True)


                # Step 2: Convert JSON to HTML
                html_prompt = JSON_TO_HTML_PROMPT.format(json.dumps(parsed_json, indent=2, ensure_ascii=False))
                html_response = call_gemini_api(
                    prompt_text=html_prompt
                )
                result = html_response['candidates'][0]['content']['parts'][0]['text']
                print("result",result)
                raw_html = result
                



            else:    

                REIMBURSEMENT_EXTRACTION_PROMPT = """
                You are an expense management assistant. Your task is to process a batch of expense documents for reimbursement. For each document, you will:
                Classify the expense type from the following categories: 'Travel', 'Food', 'Mobile', 'Stay', or 'Others'.
                Determine reimbursement eligibility: Expenses classified as 'Travel' or 'Food' are Allowed for Reimbursement. All other categories are Not Allowed for Reimbursement.
                Extract key details:
                Expense Type
                Date of Expense
                Expense Amount (in INR)
                Vendor Name
                Once all documents are processed, present the information in two distinct summary tables:
                Section 1: Allowed for Reimbursement
                This table should include all expenses eligible for reimbursement.
                Columns: 'Expense Type', 'Date', 'Expense Amount (INR)', 'Vendor'.
                Below the table, provide a 'Total Amount for Reimbursement (INR)' for this section.
                Section 2: Not Allowed for Reimbursement
                This table should include all expenses not eligible for reimbursement.
                Columns: 'Expense Type', 'Date', 'Expense Amount (INR)', 'Vendor'.
                Below the table, provide a 'Total Not Allowed (INR)' for this section.
                Ensure clarity, accuracy, and a professional format suitable for account approvers.
                dont add ```json or ``` in your response""".strip()   

                # data_part = {"mime_type": mime_type, "data": file_bytes}
                # model = genai.GenerativeModel("gemini-2.0-flash", generation_config={"response_mime_type": "application/json"})
                # # model = GenerativeModel(model_name="models/gemini-1.5-flash", generation_config={"response_mime_type": "application/json"})
                # response = model.generate_content([data_part, REIMBURSEMENT_EXTRACTION_PROMPT])
                response = call_gemini_api(
                    prompt_text=REIMBURSEMENT_EXTRACTION_PROMPT,
                    input_data=absolute_path,
                    response_mime_type="application/json"
                )
                result = response['candidates'][0]['content']['parts'][0]['text']
                # extracted_json = json.loads(result)
                # parsed_json=extracted_json
                # parsed_json = json.loads(result)
                parsed_json = safe_json_load(result)
                if parsed_json is None:
                    logger.error("Invalid JSON received. Cannot parse JSON.", exc_info=True)
                    return Response({"error": "Invalid JSON received"}, status=400)

                if 'usageMetadata' in response:
                    usage_metadata = response['usageMetadata']
                    input_tokens = usage_metadata.get('promptTokenCount', 0)
                    output_tokens = usage_metadata.get('candidatesTokenCount', 0)
                    total_tokens = usage_metadata.get('totalTokenCount', 0)

                    logger.info(f"Input Tokens: {input_tokens}")
                    logger.info(f"Output Tokens: {output_tokens}")
                    logger.info(f"Total Tokens: {total_tokens}")
                else:
                    logger.info("Usage metadata not available in the response.")

                
                if isinstance(extracted_json, list) and extracted_json:
                    parsed_json = extracted_json[0]

                     # Step 2: Convert JSON to HTML
                html_prompt = JSON_TO_HTML_PROMPT.format(json.dumps(parsed_json, indent=2, ensure_ascii=False))
                html_response = call_gemini_api(
                    prompt_text=html_prompt
                )
                result = html_response['candidates'][0]['content']['parts'][0]['text']
                raw_html = result     
    

            # Handle if the HTML comes as a JSON stringified list
            try:
                maybe_list = json.loads(raw_html)
                if isinstance(maybe_list, list):
                    html_content = "".join(maybe_list)
                else:
                    html_content = str(maybe_list)
            except json.JSONDecodeError:
                html_content = raw_html

            # Save extracted JSON to file
            json_filename = os.path.splitext(relative_path)[0] + ".json"
            json_path = os.path.join(settings.MEDIA_ROOT, json_filename)
            with open(json_path, "w", encoding="utf-8") as jf:
                json.dump(parsed_json, jf, indent=2, ensure_ascii=False)

            # Save record to database
            doc = Document.objects.create(
                filepath=relative_path,
                file=relative_path,
                json_data=parsed_json,
                html_content=html_content,
                userid_id=user_id,
                document_type=doc_type,  # Save file type here
                input_token = input_tokens,
                output_token = output_tokens
            )

            encrypted_doc_id = encrypt_id(doc.id)
            logger.info(f"Document processed and saved successfully. Document ID: {encrypted_doc_id}")

            return Response({
                "status": "success",
                "document_id": encrypted_doc_id,
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(status.HTTP_500_INTERNAL_SERVER_ERROR, exc_info=True)
            logger.error("Error while processing document.", exc_info=True)
            log_exception(logger)
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class UploadAndValidateReimbursementView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        uploaded_file = request.FILES.get("file")
        user_id = request.POST.get("user_id")
        document_id = request.POST.get("document_id")

        if not uploaded_file or not user_id:
            return Response({"error": "Missing file or user_id"}, status=400)

        try:
            # Save file
            file_name = uploaded_file.name
            extension = os.path.splitext(file_name)[1].lower()
            folder = "uploads/reimbursement"
            file_path = default_storage.save(os.path.join(folder, file_name), uploaded_file)
            full_path = os.path.join(settings.MEDIA_ROOT, file_path)

            # Prepare file data
            if extension in [".jpg", ".jpeg", ".png"]:
                img = Image.open(full_path)
                buffer = BytesIO()
                img.save(buffer, format=img.format)
                file_bytes = buffer.getvalue()
                mime_type = f"image/{img.format.lower()}"
            elif extension == ".pdf":
                with open(full_path, "rb") as f:
                    file_bytes = f.read()
                mime_type = "application/pdf"
            else:
                return Response({"error": "Unsupported file type"}, status=400)

            # Gemini prompt for extraction
            REIMBURSEMENT_EXTRACTION_PROMPT = """You are an expense management assistant. Your task is to process a batch of expense documents for reimbursement. For each document, you will:
                Classify the expense type from the following categories: 'Travel', 'Food', 'Mobile', 'Stay', or 'Others'.
                Determine reimbursement eligibility: Expenses classified as 'Travel' or 'Food' are Allowed for Reimbursement. All other categories are Not Allowed for Reimbursement.
                Extract key details:
                Expense Type
                Date of Expense
                Expense Amount (in INR)
                Vendor Name
                Once all documents are processed, present the information in two distinct summary tables:
                Section 1: Allowed for Reimbursement
                This table should include all expenses eligible for reimbursement.
                Columns: 'Expense Type', 'Date', 'Expense Amount (INR)', 'Vendor'.
                Below the table, provide a 'Total Amount for Reimbursement (INR)' for this section.
                Section 2: Not Allowed for Reimbursement
                This table should include all expenses not eligible for reimbursement.
                Columns: 'Expense Type', 'Date', 'Expense Amount (INR)', 'Vendor'.
                Below the table, provide a 'Total Not Allowed (INR)' for this section.
                Ensure clarity, accuracy, and a professional format suitable for account approvers.""".strip()   

            # Step 1: Extract JSON
            response = call_gemini_api(
                prompt_text=REIMBURSEMENT_EXTRACTION_PROMPT,
                input_data=file_path,
                response_mime_type="application/json"
            )
            result = response['candidates'][0]['content']['parts'][0]['text']
            extracted_json = safe_json_load(result)

            if isinstance(extracted_json, list) and extracted_json:
                extracted_json = extracted_json[0]

            # Step 2: Convert JSON to HTML
            JSON_TO_HTML_PROMPT = """ 
            You are an expert at converting structured JSON data into a complete, human-readable, and printable HTML document. 

            Your task is to generate a **fully styled and structured HTML report** using the provided JSON data. 

            Requirements: 
            1. Wrap the entire content in `<!DOCTYPE html>`, `<html>`, `<head>`, and `<body>` tags. 
            2. Inside the `<head>`: 
            - Add a `<meta charset="UTF-8">` tag. 
            - Set a proper `<title>` based on the document type (e.g., "Invoice Report", "Document Analysis"). 
            - Include a `<style>` tag with CSS for layout, table formatting, and conditional formatting. 
            3. Inside the `<body>`: 
            - Use a centered `.container` div with padding, background, shadow, and max-width. 
            - Display document title and relevant header information. 
            - Show key information in structured format using `<p>`, `<h3>`, etc. 
            - Use `<table>` for tabular data with proper headers and styling. 
            - Apply appropriate CSS classes for different data types. 
            - Add professional styling with proper spacing and typography. 

            STRICT RULES: 
            - Do NOT include JavaScript or external CSS. 
            - Use only embedded CSS inside a `<style>` tag. 
            - Do NOT include forms, inputs, buttons, links, or scripts. 
            - Do NOT use markdown code blocks or ```html formatting in your response.
            - Return only the raw HTML code without any explanations, comments, or formatting.

            OUTPUT FORMAT: 
            Your response must start with:
            <!DOCTYPE html>

            And must end with:
            </html>

            Do not include any text before <!DOCTYPE html> or after </html>
            Do not wrap the HTML in markdown code blocks or any other formatting

            JSON Data: 
            {} 
            """.strip()

            prompt = JSON_TO_HTML_PROMPT.format(json.dumps(extracted_json, indent=2))
            html_response = call_gemini_api(
                prompt_text=prompt
            )
            result = html_response['candidates'][0]['content']['parts'][0]['text']
           

            # Optional: clean parsed HTML (if Gemini returns it as a list)
            try:
                parsed_html = json.loads(result)
                html_body = "".join(parsed_html) if isinstance(parsed_html, list) else parsed_html
            except Exception:
                html_body = html_response

            # Step 3: Save to DB (create or update)

        
            if document_id:
                print("test")
                print("html_body :", html_body)
                try:
                    doc_id = decrypt_id(document_id)
                    doc = Document.objects.get(id=doc_id, userid_id=user_id)
                    doc.file = file_path
                    doc.filepath = file_path
                    doc.reimbursement_data = extracted_json
                    doc.html_content = html_body
                    doc.save()
                except Document.DoesNotExist:
                    return Response({"error": "Document not found for given ID and user"}, status=404)
            else:
                doc = Document.objects.create(
                    file=file_path,
                    filepath=file_path,
                    reimbursement_data=extracted_json,
                    html_content=html_body,
                    userid_id=user_id
                )

            encrypted_doc_id = encrypt_id(doc.id)

            return Response({
                "status": "accepted",
                "message": "Reimbursement claim is valid and saved.",
                "document_id": encrypted_doc_id,
                "data": extracted_json,
                "html": html_body
            }, status=200)

        except Exception as e:
            return Response({"error": str(e)}, status=500)
