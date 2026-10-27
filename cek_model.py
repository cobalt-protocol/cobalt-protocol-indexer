import requests

url = "https://llm.chutes.ai/v1/models"

response = requests.get(url, timeout=30)
response.raise_for_status()

models = response.json().get("data", [])

for model in models:
    model_id = model.get("id", "Unknown")
    inputs = model.get("input_modalities", [])
    outputs = model.get("output_modalities", [])
    features = model.get("supported_features", [])

    categories = []

    if "text" in inputs and "text" in outputs:
        categories.append("LLM / Chat")

    if "image" in inputs:
        categories.append("Vision")

    if "audio" in inputs or "audio" in outputs:
        categories.append("Audio")

    if "video" in inputs:
        categories.append("Video")

    if "embeddings" in features or "embedding" in features:
        categories.append("Embedding")

    if "tools" in features:
        categories.append("Tool Calling")

    print(f"Model      : {model_id}")
    print(f"Kategori   : {', '.join(categories) or 'Belum diketahui'}")
    print(f"Input      : {inputs}")
    print(f"Output     : {outputs}")
    print(f"Fitur      : {features}")
    print("-" * 60)
