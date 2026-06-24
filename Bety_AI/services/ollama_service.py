import requests


OLLAMA_BASE_URL = "http://localhost:11435"
OLLAMA_MODEL = "qwen3:8b"


def consultar_qwen(prompt):
    """
    Envía un prompt a Qwen usando Ollama.
    Por ahora se conecta mediante túnel SSH local:
    localhost:11435 -> AWS localhost:11434
    """

    url = f"{OLLAMA_BASE_URL}/api/generate"

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False
    }

    response = requests.post(url, json=payload, timeout=120)
    response.raise_for_status()

    data = response.json()

    return {
        "respuesta": data.get("response", "").strip(),
        "modelo": data.get("model"),
        "done": data.get("done"),
        "done_reason": data.get("done_reason"),
        "total_duration": data.get("total_duration"),
    }