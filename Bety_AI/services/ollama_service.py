import requests
import os
from dotenv import load_dotenv


load_dotenv()

# OLLAMA_BASE_URL puede apuntar a un Ollama local o a un tunel SSH hacia AWS.
# En el flujo actual se usa qwen3:8b mediante Ollama.
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))


def consultar_qwen(prompt):
    """
    Envia un prompt a Qwen usando Ollama.
    Se conecta al servicio Ollama instalado en AWS.

    Devuelve solo los campos que Bety-AI necesita para construir respuestas
    y guardar trazas simples del modelo usado.
    """

    url = f"{OLLAMA_BASE_URL}/api/generate"

    # stream=False simplifica el consumo desde Django porque Ollama responde
    # un solo JSON con el texto completo generado por el modelo.
    # think=False es necesario porque qwen3 es un modelo hibrido de razonamiento:
    # si no se desactiva, Ollama puede devolver el bloque de pensamiento interno
    # mezclado dentro de "response", lo que se percibe como 2 respuestas seguidas.
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False
    }

    response = requests.post(url, json=payload, timeout=OLLAMA_TIMEOUT_SECONDS)
    response.raise_for_status()

    data = response.json()

    return {
        "respuesta": data.get("response", "").strip(),
        "modelo": data.get("model"),
        "done": data.get("done"),
        "done_reason": data.get("done_reason"),
        "total_duration": data.get("total_duration"),
    }
