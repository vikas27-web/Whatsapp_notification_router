import os
import csv
import json
import time
from PIL import Image
import google.generativeai as genai
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

api_key = os.environ.get("GEMINI_API_KEY")

if api_key:
    genai.configure(api_key=api_key)

class MediaPreprocessor:
    def __init__(self, dataset_dir, cache_path=None):
        self.dataset_dir = dataset_dir
        self.cache_path = cache_path or os.path.join(dataset_dir, 'media_cache.json')
        self.cache = {}
        self.load_cache()

    def load_cache(self):
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
                print(f"Loaded {len(self.cache)} items from media cache.")
            except Exception as e:
                print(f"Error loading cache: {e}. Starting fresh.")
                self.cache = {}
        else:
            self.cache = {}

    def save_cache(self):
        try:
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving cache: {e}")

    def call_gemini_with_retry(self, model, content_parts):
        max_retries = 6
        base_delay = 15
        for attempt in range(max_retries):
            try:
                response = model.generate_content(content_parts)
                return response
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "quota" in err_str.lower() or "limit" in err_str.lower():
                    # Double the sleep time each retry, starting at 20 seconds
                    sleep_time = base_delay + (attempt * 10)
                    print(f"Rate limit hit. Retrying in {sleep_time}s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(sleep_time)
                else:
                    raise e
        raise Exception("Max retries exceeded due to rate limits.")

    def process_image(self, image_id, file_path):
        if image_id in self.cache and "error" not in self.cache[image_id]:
            return self.cache[image_id]

        full_path = os.path.join(self.dataset_dir, file_path)
        if not os.path.exists(full_path):
            print(f"Image file not found: {full_path}")
            return {"error": "file_not_found", "ocr_text": "", "visual_intent": ""}

        print(f"Processing image {image_id} ({file_path})...")
        try:
            model = genai.GenerativeModel('gemini-3.5-flash-lite')
            img = Image.open(full_path)
            
            prompt = (
                "Analyze this WhatsApp image message. "
                "1. Extract any visible text verbatim (OCR).\n"
                "2. Identify the visual intent (e.g. is it a payment QR code, a banking transaction screenshot, "
                "a promotional flyer, an event notice, a forward/meme, or something else?).\n"
                "Provide the result in the following format:\n"
                "[OCR TEXT]: <extracted text>\n"
                "[VISUAL INTENT]: <brief description of visual intent>"
            )
            
            response = self.call_gemini_with_retry(model, [prompt, img])
            text_resp = response.text
            
            ocr_text = ""
            visual_intent = ""
            
            # Parse response
            if "[OCR TEXT]:" in text_resp:
                parts = text_resp.split("[VISUAL INTENT]:")
                ocr_text = parts[0].replace("[OCR TEXT]:", "").strip()
                if len(parts) > 1:
                    visual_intent = parts[1].strip()
            else:
                ocr_text = text_resp
                visual_intent = "unknown"

            result = {
                "type": "image",
                "ocr_text": ocr_text,
                "visual_intent": visual_intent,
                "raw_response": text_resp
            }
            self.cache[image_id] = result
            self.save_cache()
            time.sleep(2)  # Generous sleep to respect free-tier RPM
            return result
        except Exception as e:
            print(f"Error processing image {image_id}: {e}")
            return {"error": str(e), "ocr_text": "", "visual_intent": "error"}

    def process_voice_note(self, voice_note_id, file_path):
        if voice_note_id in self.cache and "error" not in self.cache[voice_note_id]:
            return self.cache[voice_note_id]

        full_path = os.path.join(self.dataset_dir, file_path)
        if not os.path.exists(full_path):
            print(f"Voice note file not found: {full_path}")
            return {"error": "file_not_found", "transcription": ""}

        print(f"Processing voice note {voice_note_id} ({file_path})...")
        try:
            model = genai.GenerativeModel('gemini-3.5-flash-lite')
            with open(full_path, 'rb') as f:
                audio_data = f.read()
                
            response = self.call_gemini_with_retry(model, [
                "Transcribe this voice note verbatim in its original language (likely English, Hindi, or Hinglish). "
                "Do not add any introductory or explanatory text. Just output the transcription.",
                {
                    'mime_type': 'audio/mp3',
                    'data': audio_data
                }
            ])
            
            result = {
                "type": "voice",
                "transcription": response.text.strip()
            }
            self.cache[voice_note_id] = result
            self.save_cache()
            time.sleep(2)  # Generous sleep to respect free-tier RPM
            return result
        except Exception as e:
            print(f"Error processing voice note {voice_note_id}: {e}")
            return {"error": str(e), "transcription": ""}

    def run_all(self):
        # 1. Process images.csv
        images_csv_path = os.path.join(self.dataset_dir, 'images.csv')
        if os.path.exists(images_csv_path):
            with open(images_csv_path, encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.process_image(row['image_id'], row['file_path'])

        # 2. Process voice_notes.csv
        voice_notes_csv_path = os.path.join(self.dataset_dir, 'voice_notes.csv')
        if os.path.exists(voice_notes_csv_path):
            with open(voice_notes_csv_path, encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.process_voice_note(row['voice_note_id'], row['file_path'])

if __name__ == "__main__":
    preprocessor = MediaPreprocessor('dataset')
    preprocessor.run_all()
