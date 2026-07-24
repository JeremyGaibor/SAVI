import json
import re

from .chat_respuestas_ia import limpiar_respuesta_ia


def extraer_json_desde_respuesta_ia(respuesta):
    texto = limpiar_respuesta_ia(str(respuesta or "")).strip()
    texto = re.sub(r"^```(?:json)?\s*", "", texto)
    texto = re.sub(r"\s*```$", "", texto)

    inicio = texto.find("{")
    fin = texto.rfind("}")

    if inicio != -1 and fin != -1 and fin > inicio:
        texto = texto[inicio:fin + 1]

    return json.loads(texto)
