import os
import google.generativeai as genai
from dotenv import load_dotenv

# Load env variables
load_dotenv()

api_key = os.environ.get("GEMINI_API_KEY")
print(f"Loaded API key: {api_key[:8]}... (length: {len(api_key)})")

# Configure library
genai.configure(api_key=api_key)

try:
    print("Testing connection with gemini-1.5-flash...")
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content("Say hello in one word.")
    print("Success!")
    print(f"Model response: {response.text.strip()}")
except Exception as e:
    print(f"Error occurred: {e}")
