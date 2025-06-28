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
from django.shortcuts import get_object_or_404, render

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

# Global prompt for JSON to HTML conversion
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
            return JsonResponse({"error": "File not found"}, status=status.HTTP_404_NOT_FOUND)

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return JsonResponse(data, safe=False)

    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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

        except InvalidToken:
            logger.error("Invalid or corrupted document ID provided.", exc_info=True)
            return Response(
                {"error": "Invalid or corrupted document ID"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception:
            logger.error("Error while fetching document by ID", exc_info=True)
            log_exception(logger)       # ⬅️  full traceback to file
            return Response(
                {"error": "An internal server error occurred while retrieving the document."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class UserDocumentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            logger.info(f"UserDocumentView accessed by user ID: {user.id}")

            # Assuming user.id == 2 is an admin user
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
            return Response({"error": "Missing required fields"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            decrypted_id = decrypt_id(encrypted_id)
        except InvalidToken:
            return Response({"error": "Invalid encrypted ID"}, status=status.HTTP_400_BAD_REQUEST)

        doc = get_object_or_404(Document, id=decrypted_id, userid_id=user_id)
        json_data = doc.json_data

        prompt = JSON_TO_HTML_PROMPT.format(json.dumps(json_data, indent=2))

        try:
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
            except Exception: # Catch broader exceptions during parsing
                html_body = raw_html

            # Final cleanup
            html_body = html_body.replace("\\n", "").replace("\n", "").replace('\\"', '"')

            return render(request, 'rendered_html.html', {'html_body': html_body})
        except Exception as e:
            logger.error(f"Error rendering JSON to HTML: {e}", exc_info=True)
            log_exception(logger)
            return Response(
                {"error": f"An error occurred while rendering HTML: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class UploadAndProcessFileView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        uploaded_file = request.FILES.get("pdf_file")
        prompt_text = request.POST.get("prompt_text")
        user_id = request.POST.get("user_id")
        doc_type = request.POST.get("doc_type")

        logger.info("Upload request received")

        input_tokens = 0 # Initialize with default value
        output_tokens = 0 # Initialize with default value

        if not uploaded_file:
            logger.error("Upload failed: 'pdf_file' is missing in the request.", exc_info=True)
            return Response(
                {"status": "error", "message": "Missing 'pdf_file'"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Set default prompt text based on doc_type if not provided
        if not prompt_text:
            if doc_type == 'docextraction':
                prompt_text = (
                    "You are an intelligent data extraction model. Extract all relevant structured "
                    "data from the invoice provided. Identify and capture any key information that "
                    "would typically be found on a commercial invoice, such as metadata, party details, "
                    "line items, totals, and any other meaningful elements. Present the extracted data "
                    "in a structured JSON format."
                    "dont add ```json or ``` in your response"
                )
            elif doc_type == 'reimbursement':
                # Moved REIMBURSEMENT_EXTRACTION_PROMPT here to avoid duplication
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
                prompt_text = REIMBURSEMENT_EXTRACTION_PROMPT
            else:
                logger.warning(f"No specific prompt provided for doc_type: {doc_type}. Using generic prompt.")
                prompt_text = "Extract all structured data from the document in JSON format."


        try:
            # Save uploaded file
            custom_dir = "uploads/pdf_files"
            save_dir = os.path.join(settings.MEDIA_ROOT, custom_dir)
            os.makedirs(save_dir, exist_ok=True)

            file_name = uploaded_file.name
            extension = os.path.splitext(file_name)[1].lower()
            relative_path = default_storage.save(os.path.join(custom_dir, file_name), uploaded_file)
            absolute_path = os.path.join(settings.MEDIA_ROOT, relative_path)

            if extension not in [".jpg", ".jpeg", ".png", ".pdf"]:
                logger.error("Unsupported file type provided.", exc_info=True)
                return Response(
                    {"status": "error", "message": "Unsupported file type"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Step 1: Extract structured JSON
            try:
                response = call_gemini_api(
                    prompt_text=prompt_text,
                    input_data=absolute_path,
                    response_mime_type="application/json"
                )
                
                if not response or 'candidates' not in response:
                    logger.error("Invalid API response format for JSON extraction.", exc_info=True)
                    return Response({"error": "Invalid API response format"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
                try:
                    # Get the response text
                    result_json = response['candidates'][0]['content']['parts'][0]['text']
                    logger.debug(f"Raw JSON API response: {result_json[:200]}...")  # Log first 200 chars for debugging
                    
                    if not result_json:
                        logger.error("Empty JSON response from API.", exc_info=True)
                        return Response({"error": "Empty JSON response from API"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                    
                    # Try to parse JSON with our safe parser
                    parsed_json = safe_json_load(result_json)
                    
                    if parsed_json is None:
                        logger.error("Failed to parse JSON: Invalid JSON format", exc_info=True)
                        return Response({"error": "Invalid JSON format received from API"}, status=status.HTTP_400_BAD_REQUEST)
                    
                    # Handle cases where the model might return a list with a single dictionary
                    if isinstance(parsed_json, list) and parsed_json:
                        parsed_json = parsed_json[0]

                    if not isinstance(parsed_json, dict):
                        logger.error("Parsed JSON is not a dictionary.", exc_info=True)
                        return Response({"error": "Invalid JSON format received from API"}, status=status.HTTP_400_BAD_REQUEST)

                    logger.debug("Successfully parsed JSON response")
                    
                except KeyError as e:
                    logger.error(f"Missing key in API response: {str(e)}", exc_info=True)
                    return Response({"error": "Invalid API response format"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                except Exception as e:
                    logger.error(f"Unexpected error processing API response: {str(e)}", exc_info=True)
                    return Response({"error": "Error processing API response"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            except json.JSONDecodeError as e:
                logger.error(f"JSON decoding error during extraction: {str(e)}", exc_info=True)
                return Response({"error": "Invalid JSON received from API"}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                logger.error(f"Error during JSON extraction API call: {str(e)}", exc_info=True)
                return Response({"error": f"Error during JSON extraction: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # --- HIGHLIGHT: Consistent Metadata Extraction ---
            if 'usageMetadata' in response:
                usage_metadata = response['usageMetadata']
                input_tokens = usage_metadata.get('promptTokenCount', 0)
                output_tokens = usage_metadata.get('candidatesTokenCount', 0)
                logger.info(f"JSON Extraction - Input Tokens: {input_tokens}, Output Tokens: {output_tokens}")
            else:
                logger.info("JSON Extraction - Usage metadata not available in the response.")
            # --- END HIGHLIGHT ---

            # Step 2: Convert JSON to HTML
            html_prompt = JSON_TO_HTML_PROMPT.format(json.dumps(parsed_json, indent=2, ensure_ascii=False))
            
            try:
                html_response_obj = call_gemini_api(
                    prompt_text=html_prompt
                )
                result_html = html_response_obj['candidates'][0]['content']['parts'][0]['text']
                # logger.debug(f"Raw HTML API response: {result_html}")

                # Handle if the HTML comes as a JSON stringified list
                try:
                    maybe_list = json.loads(result_html)
                    if isinstance(maybe_list, list):
                        html_content = "".join(maybe_list)
                    else:
                        html_content = str(maybe_list)
                except json.JSONDecodeError:
                    html_content = result_html # If not JSON, use as is

                # Final cleanup for HTML content
                html_content = html_content.replace("\\n", "").replace("\n", "").replace('\\"', '"')

            except Exception as e:
                logger.error(f"Error during HTML conversion API call: {str(e)}", exc_info=True)
                return Response({"error": f"Error during HTML conversion: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
                input_token = input_tokens, # --- HIGHLIGHT: Save input tokens ---
                output_token = output_tokens # --- HIGHLIGHT: Save output tokens ---
            )

            encrypted_doc_id = encrypt_id(doc.id)
            logger.info(f"Document processed and saved successfully. Document ID: {encrypted_doc_id}")

            return Response({
                "status": "success",
                "document_id": encrypted_doc_id,
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error in UploadAndProcessFileView: {str(e)}", exc_info=True)
            log_exception(logger)
            return Response(
                {"status": "error", "message": f"An internal server error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class UploadAndValidateReimbursementView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        uploaded_file = request.FILES.get("file")
        user_id = request.POST.get("user_id")
        document_id = request.POST.get("document_id")

        if not uploaded_file or not user_id:
            return Response({"error": "Missing file or user_id"}, status=status.HTTP_400_BAD_REQUEST)

        input_tokens = 0 # Initialize with default value
        output_tokens = 0 # Initialize with default value

        try:
            # Save file
            file_name = uploaded_file.name
            extension = os.path.splitext(file_name)[1].lower()
            folder = "uploads/reimbursement"
            file_path = default_storage.save(os.path.join(folder, file_name), uploaded_file)
            full_path = os.path.join(settings.MEDIA_ROOT, file_path)

            if extension not in [".jpg", ".jpeg", ".png", ".pdf"]:
                return Response({"error": "Unsupported file type"}, status=status.HTTP_400_BAD_REQUEST)

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
            try:
                response = call_gemini_api(
                    prompt_text=REIMBURSEMENT_EXTRACTION_PROMPT,
                    input_data=full_path, # Use full_path for call_gemini_api
                    response_mime_type="application/json"
                )
                result = response['candidates'][0]['content']['parts'][0]['text']
                extracted_json = safe_json_load(result)

                if isinstance(extracted_json, list) and extracted_json:
                    extracted_json = extracted_json[0]
            except Exception as e:
                logger.error(f"Error during reimbursement JSON extraction: {str(e)}", exc_info=True)
                return Response({"error": f"Error during reimbursement JSON extraction: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # --- HIGHLIGHT: Consistent Metadata Extraction ---
            if 'usageMetadata' in response:
                usage_metadata = response['usageMetadata']
                input_tokens = usage_metadata.get('promptTokenCount', 0)
                output_tokens = usage_metadata.get('candidatesTokenCount', 0)
                logger.info(f"Reimbursement - Input Tokens: {input_tokens}, Output Tokens: {output_tokens}")
            else:
                logger.info("Reimbursement - Usage metadata not available in the response.")
            # --- END HIGHLIGHT ---

            # Step 2: Convert JSON to HTML
            prompt_html = JSON_TO_HTML_PROMPT.format(json.dumps(extracted_json, indent=2))
            try:
                html_response_obj = call_gemini_api(
                    prompt_text=prompt_html
                )
                result_html = html_response_obj['candidates'][0]['content']['parts'][0]['text']
                
                # Optional: clean parsed HTML (if Gemini returns it as a list)
                try:
                    parsed_html = json.loads(result_html)
                    html_body = "".join(parsed_html) if isinstance(parsed_html, list) else parsed_html
                except json.JSONDecodeError:
                    html_body = result_html # If not JSON, use as is

                # Final cleanup for HTML content
                html_body = html_body.replace("\\n", "").replace("\n", "").replace('\\"', '"')
            except Exception as e:
                logger.error(f"Error during reimbursement HTML conversion: {str(e)}", exc_info=True)
                return Response({"error": f"Error during reimbursement HTML conversion: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Step 3: Save to DB (create or update)
            if document_id:
                logger.info(f"Updating existing reimbursement document for ID: {document_id}")
                logger.debug(f"HTML Body: {html_body[:200]}...") # Log beginning of HTML
                try:
                    doc_id = decrypt_id(document_id)
                    doc = get_object_or_404(Document, id=doc_id, userid_id=user_id) 
                    doc.file = file_path
                    doc.filepath = file_path
                    doc.reimbursement_data = extracted_json
                    doc.html_content = html_body
                    doc.input_token = input_tokens # --- HIGHLIGHT: Save input tokens ---
                    doc.output_token = output_tokens # --- HIGHLIGHT: Save output tokens ---
                    doc.save()
                    logger.info(f"Updated reimbursement document {doc_id}")
                except Document.DoesNotExist:
                    logger.error(f"Document not found for ID {doc_id} and user {user_id}", exc_info=True)
                    return Response({"error": "Document not found for given ID and user"}, status=status.HTTP_404_NOT_FOUND)
                except InvalidToken:
                    logger.error(f"Invalid encrypted document ID for update: {document_id}", exc_info=True)
                    return Response({"error": "Invalid encrypted document ID for update"}, status=status.HTTP_400_BAD_REQUEST)
            else:
                logger.info("Creating new reimbursement document.")
                doc = Document.objects.create(
                    file=file_path,
                    filepath=file_path,
                    reimbursement_data=extracted_json,
                    html_content=html_body,
                    userid_id=user_id,
                    document_type='reimbursement', # Explicitly set for new docs
                    input_token=input_tokens,
                    output_token=output_tokens
                )
                logger.info(f"Created new reimbursement document {doc.id}")

            encrypted_doc_id = encrypt_id(doc.id)

            return Response({
                "status": "accepted",
                "message": "Reimbursement claim is valid and saved.",
                "document_id": encrypted_doc_id,
                "data": extracted_json,
                "html": html_body
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"An unexpected error occurred in UploadAndValidateReimbursementView: {str(e)}", exc_info=True)
            log_exception(logger)
            return Response({"error": f"An internal server error occurred: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)