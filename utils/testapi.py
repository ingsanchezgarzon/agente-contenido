import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Initialize the official Google GenAI client
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

def generate_response(user_text: str, system_instruction: str) -> str:
    """
    Calls Gemini 2.5 Flash-Lite using the official Google GenAI SDK.
    This model is optimized for speed and is the most budget-friendly ($0.10/1M tokens).
    """
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=user_text,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                max_output_tokens=1020,
                temperature=0.7
            )
        )
        return response.text
    except Exception as e:
        return f"An error occurred: {str(e)}"

# --- EXECUTION ---
if __name__ == "__main__":
    system_prompt = "You are an expert software engineer that prefers functional programming."
    user_prompt = "Write a function to swap the keys and values in a dictionary."

    print("Requesting response from Gemini 2.5 Flash-Lite...")
    result = generate_response(user_prompt, system_prompt)
    
    print("-" * 30)
    print(result)