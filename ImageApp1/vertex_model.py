import vertexai
from vertexai.generative_models import GenerativeModel, Part, GenerationConfig, HarmCategory, HarmBlockThreshold
import google.auth
import json
import base64
import mimetypes
import os
import time
import random
from typing import Union, List, Dict, Any, Optional
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()

LOCATION = os.getenv("LOCATION")
MODEL_ID = os.getenv("MODEL_ID") # This should be 'gemini-1.5-flash' in your .env
service_account_key_path = os.getenv('SERVICE_ACCOUNT_KEY_PATH')

# Initialize Vertex AI
try:
    credentials, project_id = google.auth.load_credentials_from_file(service_account_key_path)
    vertexai.init(project=project_id, location=LOCATION, credentials=credentials)
    print(f"Vertex AI initialized for project: {project_id}, location: {LOCATION}")
except Exception as e:
    print(f"Error initializing Vertex AI: {e}")
    # You might want to raise this error or handle it more robustly in production
    exit(1) # Exit if initialization fails, as API calls won't work

# Load the GenerativeModel
try:
    model = GenerativeModel(MODEL_ID)
    print(f"Using model: {MODEL_ID} in project: {project_id}, location: {LOCATION}")
except Exception as e:
    print(f"Error loading GenerativeModel '{MODEL_ID}': {e}")
    # This might indicate an incorrect MODEL_ID or permissions issue
    exit(1)


# Retry configuration
MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 1  # seconds
MAX_RETRY_DELAY = 60  # seconds
BACKOFF_FACTOR = 2

class APIRateLimitError(Exception):
    """Custom exception for API rate limiting errors"""
    pass

def exponential_backoff(retry_count):
    """Calculate delay with exponential backoff and jitter"""
    delay = min(INITIAL_RETRY_DELAY * (BACKOFF_FACTOR ** retry_count), MAX_RETRY_DELAY)
    jitter = random.uniform(0, 0.1 * delay)  # Add up to 10% jitter
    return delay + jitter

def process_input(input_data) -> Part:
    """
    Process different types of input data and return the appropriate Part for the API.
    
    Args:
        input_data: Can be a file path (str), text (str), or JSON (dict/str)
        
    Returns:
        Part: Formatted input part for the Vertex AI API
    """
    # If input is a dictionary (already parsed JSON)
    if isinstance(input_data, dict):
        return Part.from_text(json.dumps(input_data, ensure_ascii=False))
    
    # If input is a string, check if it's a file path or JSON string
    if isinstance(input_data, str):
        # Check if it's a valid file path
        if os.path.exists(input_data):
            try:
                # Try to read as binary file first
                with open(input_data, "rb") as f:
                    file_bytes = f.read()
                    
                # Get MIME type
                mime_type, _ = mimetypes.guess_type(input_data)
                if not mime_type:
                    mime_type = "application/octet-stream"
                
                return Part.from_data(file_bytes, mime_type)
            except (IOError, OSError):
                # If file read fails, treat as text
                pass
        
        # Check if it's a JSON string
        try:
            json_data = json.loads(input_data)
            return Part.from_text(json.dumps(json_data, ensure_ascii=False))
        except (json.JSONDecodeError, TypeError):
            # If not JSON, treat as plain text
            return Part.from_text(input_data)
    
    # For any other type, convert to string
    return Part.from_text(str(input_data))

def call_gemini_api(
    prompt_text: str,
    input_data: Optional[Union[str, dict, list]] = None,
    response_mime_type: Optional[str] = None,
    max_retries: int = MAX_RETRIES,
    temperature: float = 0.9,
    top_p: float = 1.0,
    top_k: int = 32,
    max_output_tokens: int = 65536
) -> Dict[str, Any]:
    """
    Call Gemini API with flexible input handling and automatic retries.
    
    Args:
        prompt_text: The prompt text to send to the model (required)
        input_data: Optional - Can be a file path (str), text (str), or JSON (dict/str)
        response_mime_type: Optional MIME type for the response
        max_retries: Maximum number of retry attempts (default: 5)
        temperature: Controls randomness in generation (0.0-1.0)
        top_p: Controls diversity via nucleus sampling (0.0-1.0)
        top_k: Controls diversity by considering top k tokens
        max_output_tokens: Maximum number of tokens to generate
        
    Returns:
        dict: API response in a format similar to the original REST API
        
    Raises:
        APIRateLimitError: If rate limited and max retries exceeded
        Exception: For other API errors
    """
    
    for attempt in range(max_retries + 1):
        try:
            # Process the input data if provided
            content_parts = []
            
            if input_data is not None:
                # Handle multiple inputs (list/tuple)
                if isinstance(input_data, (list, tuple)):
                    for item in input_data:
                        content_parts.append(process_input(item))
                else:
                    content_parts.append(process_input(input_data))
            
            # Add prompt text (required)
            if not prompt_text and not content_parts:
                raise ValueError("Either prompt_text or input_data must be provided")
                
            if prompt_text:
                content_parts.append(Part.from_text(prompt_text))
            
            # Configure generation parameters
            generation_config = GenerationConfig(
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                max_output_tokens=max_output_tokens,
            )
            
            # Add response MIME type if specified
            if response_mime_type:
                generation_config.response_mime_type = response_mime_type
            
            response = model.generate_content(
                contents=content_parts,
                generation_config=generation_config,
                stream=False
            )
            
            # Format response to match the original API structure
            formatted_response = {
                "candidates": [],
                "promptFeedback": {
                    "blockReason": response.prompt_feedback.block_reason.name if response.prompt_feedback and response.prompt_feedback.block_reason else None,
                    "safetyRatings": []
                },
                # --- HIGHLIGHT: Add usageMetadata here ---
                "usageMetadata": {
                    "promptTokenCount": response.usage_metadata.prompt_token_count if response.usage_metadata else 0,
                    "candidatesTokenCount": response.usage_metadata.candidates_token_count if response.usage_metadata else 0,
                    "totalTokenCount": response.usage_metadata.total_token_count if response.usage_metadata else 0,
                }
                # --- END HIGHLIGHT ---
            }
            
            # Add prompt feedback safety ratings if available
            if response.prompt_feedback and response.prompt_feedback.safety_ratings:
                for rating in response.prompt_feedback.safety_ratings:
                    formatted_response["promptFeedback"]["safetyRatings"].append({
                        "category": rating.category.name,
                        "probability": rating.probability.name,
                        "blocked": rating.blocked
                    })
            
            # Process candidates
            if response.candidates:
                for candidate in response.candidates:
                    candidate_data = {
                        "content": {
                            "parts": [],
                            "role": "model"
                        },
                        "finishReason": candidate.finish_reason.name if candidate.finish_reason else None,
                        "safetyRatings": []
                    }
                    
                    # Add text content if available
                    if candidate.content and candidate.content.parts:
                        for part in candidate.content.parts:
                            if hasattr(part, 'text') and part.text:
                                candidate_data["content"]["parts"].append({"text": part.text})
                    
                    # Add safety ratings
                    if candidate.safety_ratings:
                        for rating in candidate.safety_ratings:
                            candidate_data["safetyRatings"].append({
                                "category": rating.category.name,
                                "probability": rating.probability.name,
                                "blocked": rating.blocked
                            })
                    
                    formatted_response["candidates"].append(candidate_data)
            
            return formatted_response
            
        except Exception as e:
            error_str = str(e).lower()
            
            # Check for rate limiting or quota errors
            if any(term in error_str for term in ['rate limit', 'quota', '429', 'resource exhausted']):
                if attempt < max_retries:
                    retry_delay = exponential_backoff(attempt)
                    print(f"Rate limited. Retrying in {retry_delay:.2f} seconds... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    continue
                else:
                    raise APIRateLimitError(
                        f"Max retries ({max_retries}) exceeded due to rate limiting. "
                        f"Please wait before making more requests."
                    )
            
            # For other errors, retry with exponential backoff
            if attempt < max_retries:
                retry_delay = exponential_backoff(attempt)
                print(f"Request failed: {str(e)}. Retrying in {retry_delay:.2f} seconds... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
                continue
            
            raise Exception(f"API request failed after {max_retries} retries: {str(e)}")

def call_gemini_api_with_file(
    file_path: str, 
    prompt_text: str, 
    response_mime_type: Optional[str] = None, 
    max_retries: int = MAX_RETRIES
) -> Dict[str, Any]:
    """
    Legacy function for backward compatibility.
    Use call_gemini_api() for more flexible input handling.
    """
    return call_gemini_api(
        prompt_text=prompt_text, 
        input_data=file_path, 
        response_mime_type=response_mime_type,
        max_retries=max_retries
    )