import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("GROQ_API_KEY")

client = Groq(api_key=api_key)
models_to_test = ["groq/compound", "openai/gpt-oss-20b", "qwen/qwen3.6-27b"]
for model in models_to_test:
    try:
        probe = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with: OK"}],
            max_tokens=5,
        )
        print("Success for", model, ":", probe.choices[0].message.content)
    except Exception as e:
        print("Error for", model, ":", e)
