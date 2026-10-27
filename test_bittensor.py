import os
import requests
from dotenv import load_dotenv

load_dotenv()


class ChutesLoadBalancer:
    def __init__(self):
        self.api_key = os.getenv("CHUTES_API_KEY")

        if not self.api_key:
            raise ValueError("Missing CHUTES_API_KEY in .env")

        self.base_url = "https://llm.chutes.ai/v1"
        self.models_url = f"{self.base_url}/models"
        self.chat_url = f"{self.base_url}/chat/completions"

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        self.health_timeout = 15
        self.chat_timeout = 60
        self.selected_model = None

    def get_available_models(self):
        """Ambil kandidat model LLM dari katalog Chutes."""
        response = requests.get(
            self.models_url,
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()

        models = []

        for item in response.json().get("data", []):
            model_id = item.get("id")

            if not model_id:
                continue

            inputs = item.get("input_modalities")
            outputs = item.get("output_modalities")
            features = item.get("supported_features", [])

            if inputs is not None and "text" not in inputs:
                continue

            if outputs is not None and "text" not in outputs:
                continue

            # Lewati model embedding jika metadata menunjukkannya.
            if any("embed" in str(feature).lower() for feature in features):
                continue

            models.append(model_id)

        return models

    def is_model_healthy(self, model_id):
        """Tes apakah model bisa menghasilkan respons chat."""
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": "Reply with OK."}],
            "stream": False,
            "max_tokens": 8,
            "temperature": 0,
        }

        try:
            response = requests.post(
                self.chat_url,
                headers=self.headers,
                json=payload,
                timeout=self.health_timeout,
            )

            if not response.ok:
                print(f"[SKIP] {model_id}: " f"HTTP {response.status_code}")
                return False

            result = response.json()
            choices = result.get("choices", [])

            if not choices:
                print(f"[SKIP] {model_id}: no response")
                return False

            content = choices[0].get("message", {}).get("content")

            if not isinstance(content, str) or not content.strip():
                print(f"[SKIP] {model_id}: empty response")
                return False

            print(f"[READY] {model_id}")
            return True

        except (requests.RequestException, ValueError) as exc:
            print(f"[SKIP] {model_id}: {exc}")
            return False

    def find_first_healthy_model(self):
        """Cari model sehat dan berhenti pada model pertama."""
        models = self.get_available_models()

        if not models:
            raise RuntimeError("No candidate models found.")

        print(f"Available candidates: {len(models)}")

        for model_id in models:
            print(f"[CHECK] {model_id}")

            if self.is_model_healthy(model_id):
                self.selected_model = model_id
                return model_id

        raise RuntimeError("No healthy LLM model found.")

    def chat(self, message, model_id=None):
        """Kirim prompt ke model terpilih atau model yang ditentukan."""
        if model_id is None:
            model_id = self.selected_model

        if model_id is None:
            model_id = self.find_first_healthy_model()

        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": message}],
            "stream": False,
            "max_tokens": 1024,
            "temperature": 0.7,
        }

        response = requests.post(
            self.chat_url,
            headers=self.headers,
            json=payload,
            timeout=self.chat_timeout,
        )
        response.raise_for_status()

        result = response.json()
        choices = result.get("choices", [])

        if not choices:
            raise RuntimeError(f"{model_id} returned no choices.")

        content = choices[0].get("message", {}).get("content")

        if not isinstance(content, str) or not content.strip():
            raise RuntimeError(f"{model_id} returned an empty response.")

        return content


if __name__ == "__main__":
    llm = ChutesLoadBalancer()

    # Cari model sehat terlebih dahulu.
    model = llm.find_first_healthy_model()
    print(f"\nSelected model: {model}")

    # Kirim prompt pengguna ke model yang terpilih.
    prompt = input("\nMasukkan prompt: ")
    answer = llm.chat(prompt)

    print("\n=== RESULT ===")
    print(answer)
