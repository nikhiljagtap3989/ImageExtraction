import os
import json
from dotenv import load_dotenv
from google.oauth2 import service_account
import google.generativeai as genai

load_dotenv()
service_account_path = os.getenv("VERTEX_SERVICE_ACCOUNT")

if not service_account_path or not os.path.exists(service_account_path):
    raise RuntimeError("VERTEX_SERVICE_ACCOUNT path is not set or invalid")

credentials = service_account.Credentials.from_service_account_file(
    service_account_path,
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)

genai.configure(credentials=credentials)

model = genai.GenerativeModel("models/gemini-1.5-flash")

response = model.generate_content("Tell me a Python joke.")
print(response.text)
