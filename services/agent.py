# services/agent.py

import os
import openai
from dotenv import load_dotenv

# Load secrets from .env
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def ask_agent(prompt: str) -> str:
    response = openai.ChatCompletion.create(
        model="gpt-4",  # or "gpt-3.5-turbo"
        messages=[
            {"role": "system", "content": "You are Echo, an expert assistant for off-grid solar, Bitcoin mining, and smart automation."},
            {"role": "user", "content": prompt},
        ]
    )
    return response.choices[0].message["content"]

