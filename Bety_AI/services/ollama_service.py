from .llm_provider import generar_texto


def consultar_qwen(prompt):
    """
    Genera texto vía el proveedor LLM configurado (LLM_PROVIDER/LLM_FALLBACK_PROVIDER,
    ver services/llm_provider.py). El nombre y la forma del dict devuelto se
    mantienen por compatibilidad con los callers existentes; "done"/"done_reason"/
    "total_duration" son especificos de la API de Ollama y quedan en None cuando
    responde otro proveedor.
    """
    resultado = generar_texto(prompt)
    return {
        "respuesta": resultado["respuesta"],
        "modelo": resultado["modelo"],
        "done": None,
        "done_reason": None,
        "total_duration": None,
    }
