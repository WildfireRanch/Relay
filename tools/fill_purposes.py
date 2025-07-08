# File: tools/fill_purposes.py
# Purpose: Uses GPT to generate a Purpose line for every file in metadata.json

from dotenv import load_dotenv
load_dotenv()
import os
print("🔍 ENV KEY:", os.getenv("OPENAI_API_KEY"))
import json
from pathlib import Path
from time import sleep
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def ask_gpt_for_purpose(entry):
    prompt = f"""
You're a senior software engineer reviewing Python files in a production-grade codebase.

Your task is to write a concise `# Purpose:` line that explains what the file is for.
This should be high-level, ideally one sentence, and describe the *role* this file plays in the system.

Return only the Purpose line (no filename, no explanations, no formatting).

Filename: {entry['file']}
Contents: {entry.get('contents', [])}
Imports: {entry.get('imports', [])}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "You are helping document a Python codebase."},
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.4,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ Error on {entry['file']}: {e}")
        return "<PURPOSE ERROR>"

def main():
    input_path = Path("tools/metadata.json")
    output_path = Path("tools/metadata_with_purpose.json")

    with open(input_path, "r") as f:
        metadata = json.load(f)

    enriched = []
    for entry in metadata:
        purpose = ask_gpt_for_purpose(entry)
        print(f"✅ {entry['file']}: {purpose}")
        entry["purpose"] = purpose
        enriched.append(entry)
        sleep(0.5)  # polite rate limit buffer

    with open(output_path, "w") as f:
        json.dump(enriched, f, indent=2)

    print(f"\n🎉 All purposes written to {output_path}")

if __name__ == "__main__":
    main()
