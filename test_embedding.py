import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("CHUTES_API_KEY")

if not API_KEY:
    raise ValueError("Missing CHUTES_API_KEY in .env")

MODEL = "chutes-qwen-qwen3-embedding-8b-tee"
EMBEDDINGS_URL = "https://chutes-qwen-qwen3-embedding-8b-tee.chutes.ai/v1/embeddings"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


def embed_text(text: str) -> list[float]:
    response = requests.post(
        EMBEDDINGS_URL,
        headers=HEADERS,
        json={
            "model": MODEL,
            "input": text,
        },
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            f"Embedding failed: HTTP {response.status_code}\n"
            f"Response: {response.text}"
        )

    result = response.json()
    data = result.get("data", [])

    if not data:
        raise RuntimeError(f"No embedding returned: {result}")

    embedding = data[0].get("embedding")

    if not isinstance(embedding, list) or not embedding:
        raise RuntimeError(f"Invalid embedding response: {result}")

    return embedding


if __name__ == "__main__":
    text = "Presiden pertama Indonesia adalah Soekarno."

    vector = embed_text(text)

    print("Model:", MODEL)
    print("Text:", text)
    print("Dimensions:", len(vector))
    print("First 10 values:", vector[:10])
