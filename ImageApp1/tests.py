from django.test import TestCase


# Create your tests here.
import os
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types
import prompt  # Make sure this contains `Extraction_Prompt`

# Load environment variables from .env
load_dotenv()

# Fetch API key from environment
api_key = os.getenv("GOOGLE_API_KEY")

# Initialize Gemini client
client = genai.Client(api_key=api_key)

# Path to the single image
image_path = r"D:\Mukul\DocEdge_workplace\AE_Workplace\DocEdge_R&D\Projects\DE_to_HTML\handwrittensample.pdf"

try:
    # Upload the image
    uploaded_file = client.files.upload(file=image_path)

    # Generate content using the model
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        config={'response_mime_type': 'application/json'},
        contents=[uploaded_file, prompt.Application_Form],
    )

    # # Create output JSON path with the same filename
    # output_json_path = os.path.splitext(image_path)[0] + ".json"
    

    # # Save response to JSON file
    # with open(output_json_path, "w", encoding="utf-8") as f:
    #     json.dump({"response": response.text}, f, indent=2)
     # Save output as HTML
    output_html_path = os.path.splitext(image_path)[0] + ".html"
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(response.text)
        
        
    
    print(f"Output saved to: {output_html_path}")

except Exception as e:
    print(f"Error processing the image: {e}")
