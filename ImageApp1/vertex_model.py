import requests
import google.oauth2.service_account
from google.auth.transport.requests import Request as GoogleAuthRequest
import json
import base64
import mimetypes
import os
from dotenv import load_dotenv



# # Only prompt (no input data)
# result1 = call_gemini_api("Tell me a joke")

# # Prompt with file
# result2 = call_gemini_api("Analyze this document", input_data="path/to/file.pdf")

# # Prompt with text
# result3 = call_gemini_api("Summarize this text", input_data="Long text to summarize...")

# # Prompt with JSON
# result4 = call_gemini_api("Process this data", input_data={"key": "value"})

# # Using the legacy function (still works the same way)
# result5 = call_gemini_api_with_file("path/to/file.pdf", "Analyze this document")


# Load environment variables
load_dotenv()

location = os.getenv('LOCATION')
model_id = os.getenv('MODEL_ID')
service_account_key_path = os.getenv('SERVICE_ACCOUNT_KEY_PATH')

def get_auth_details(service_account_key_path, scopes):
    """Get authentication token and project ID"""
    if not os.path.exists(service_account_key_path):
        raise FileNotFoundError(f"Service account key file not found at: {service_account_key_path}")
    
    try:
        with open(service_account_key_path, 'r') as file:
            service_account_data = json.load(file)
        
        project_id = service_account_data.get("project_id")
        if not project_id:
            raise ValueError("Project ID not found in service account key file.")
        
        credentials = google.oauth2.service_account.Credentials.from_service_account_file(
            service_account_key_path,
            scopes=scopes
        )
        credentials.refresh(GoogleAuthRequest())
        
        access_token = credentials.token
        if not access_token:
            raise Exception("Access token generation failed: Token is None.")
        
        return access_token, project_id
    except Exception as e:
        raise Exception(f"Authentication failed: {e}")

def process_input(input_data):
    """
    Process different types of input data and return the appropriate format for the API.
    
    Args:
        input_data: Can be a file path (str), text (str), or JSON (dict/str)
        
    Returns:
        dict: Formatted input parts for the API
    """
    # If input is a dictionary (already parsed JSON)
    if isinstance(input_data, dict):
        return {"text": json.dumps(input_data, ensure_ascii=False)}
    
    # If input is a string, check if it's a file path or JSON string
    if isinstance(input_data, str):
        # Check if it's a valid file path
        if os.path.exists(input_data):
            try:
                # Try to read as binary file first
                with open(input_data, "rb") as f:
                    file_bytes = f.read()
                    file_base64 = base64.b64encode(file_bytes).decode("utf-8")
                    
                # Get MIME type
                mime_type, _ = mimetypes.guess_type(input_data)
                if not mime_type:
                    mime_type = "application/octet-stream"
                
                return {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": file_base64
                    }
                }
            except (IOError, OSError):
                # If file read fails, treat as text
                pass
        
        # Check if it's a JSON string
        try:
            json_data = json.loads(input_data)
            return {"text": json.dumps(json_data, ensure_ascii=False)}
        except (json.JSONDecodeError, TypeError):
            # If not JSON, treat as plain text
            return {"text": input_data}
    
    # For any other type, convert to string
    return {"text": str(input_data)}

def call_gemini_api(
    prompt_text,
    input_data=None,
    response_mime_type=None
):
    """
    Call Gemini API with flexible input handling.
    
    Args:
        prompt_text: The prompt text to send to the model (required)
        input_data: Optional - Can be a file path (str), text (str), or JSON (dict/str)
        response_mime_type: Optional MIME type for the response
        
    Returns:
        dict: API response
    """
    scopes = ['https://www.googleapis.com/auth/cloud-platform']
    access_token, project_id = get_auth_details(service_account_key_path, scopes)
    
    API_ENDPOINT = (
        f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/"
        f"locations/{location}/publishers/google/models/{model_id}:generateContent"
    )
    
    # Process the input data if provided
    input_parts = []
    
    if input_data is not None:
        # Handle multiple inputs (list/tuple)
        if isinstance(input_data, (list, tuple)):
            for item in input_data:
                input_parts.append(process_input(item))
        else:
            input_parts.append(process_input(input_data))
    
    # Add prompt text (required)
    if not prompt_text and not input_parts:
        raise ValueError("Either prompt_text or input_data must be provided")
        
    if prompt_text:
        input_parts.append({"text": prompt_text})
    
    contents = [
        {
            "role": "user",
            "parts": input_parts
        }
    ]
    
    payload = {
        "contents": contents
    }
    
    if response_mime_type:
        payload["generationConfig"] = {
            "responseMimeType": response_mime_type
        }
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(API_ENDPOINT, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        error_msg = f"API request failed: {str(e)}"
        if hasattr(e, 'response') and e.response is not None:
            error_msg += f"\nResponse: {e.response.text}"
        raise Exception(error_msg)

def call_gemini_api_with_file(file_path, prompt_text, response_mime_type=None):
    """
    Legacy function for backward compatibility.
    Use call_gemini_api() for more flexible input handling.
    """
    return call_gemini_api(prompt_text=prompt_text, input_data=file_path, response_mime_type=response_mime_type)