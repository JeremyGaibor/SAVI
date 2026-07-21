import json
import re

from ..services.ollama_service import consultar_qwen
from .chat_respuestas_ia import limpiar_respuesta_ia
from .contexto_usuario import limpiar_texto_contexto


FORMATOS_RESPUESTA = {"normal", "tabla", "lista", "pasos", "resumen"}
TIPOS_OPERACION = {
    "consulta_documental",
    "reformulacion",
    "historial",
    "fuera_ambito",
}


def extraer_json_interpretacion(respuesta):
    texto = limpiar_respuesta_ia(str(respuesta or "")).strip()
    texto = re.sub(r"^```(?:json)?\s*", "", texto)
    texto = re.sub(r"\s*```$", "", texto)

    inicio = texto.find("{")
    fin = texto.rfind("}")

    if inicio != -1 and fin != -1 and fin > inicio:
        texto = texto[inicio:fin + 1]

    return json.loads(texto)


def normalizar_lista_texto(valor, limite=8):
    if not isinstance(valor, list):
        return []

    elementos = []
    for item in valor[:limite]:
        texto = limpiar_texto_contexto(item, 80)
        if texto:
            elementos.append(texto)

    return elementos


def normalizar_tipo_operacion(valor):
    tipo = limpiar_texto_contexto(valor, 40).lower()
    if tipo in TIPOS_OPERACION:
        return tipo
    return "consulta_documental"


def normalizar_formato_respuesta(valor):
    formato = limpiar_texto_contexto(valor, 30).lower()
    if formato in FORMATOS_RESPUESTA:
        return formato
    return "normal"


def normalizar_filtros_sugeridos(valor):
    if not isinstance(valor, dict):
        return {}

    filtros = {}
    campos_permitidos = [
        "ambito",
        "estado_vigencia",
        "rol",
        "facultad",
        "carrera",
        "tipo_documento",
        "id_documento",
        "grupo",
    ]

    for campo in campos_permitidos:
        texto = limpiar_texto_contexto(valor.get(campo), 120)
        if not texto:
            continue
        filtros[campo] = texto if campo == "id_documento" else texto.upper()

    return filtros


def normalizar_interpretacion(data, pregunta):
    if not isinstance(data, dict):
        data = {}

    pregunta_limpia = limpiar_texto_contexto(pregunta, 500)
    consulta_normalizada = limpiar_texto_contexto(
        data.get("consulta_normalizada") or pregunta_limpia,
        600,
    )
    palabras_clave = normalizar_lista_texto(data.get("palabras_clave"))

    partes_busqueda = [pregunta_limpia, consulta_normalizada]
    partes_busqueda.extend(palabras_clave)
    consulta_busqueda = " ".join(parte for parte in partes_busqueda if parte)

    return {
        "tipo_operacion": normalizar_tipo_operacion(data.get("tipo_operacion")),
        "consulta_normalizada": consulta_normalizada,
        "consulta_busqueda": limpiar_texto_contexto(consulta_busqueda, 1000),
        "depende_historial": bool(data.get("depende_historial", False)),
        "formato_respuesta": normalizar_formato_respuesta(data.get("formato_respuesta")),
        "palabras_clave": palabras_clave,
        "filtros_sugeridos": normalizar_filtros_sugeridos(data.get("filtros_sugeridos")),
        "modelo": data.get("modelo"),
    }


def interpretar_consulta_ia(pregunta, historial="", contexto_usuario=""):
    pregunta_limpia = limpiar_texto_contexto(pregunta, 500)
    historial_limpio = limpiar_texto_contexto(historial, 1800)
    contexto_limpio = limpiar_texto_contexto(contexto_usuario, 1000)

    prompt = f"""
Eres un clasificador de consultas para Bety-AI, un asistente documental del SGA UTEQ.

No respondas al usuario. Devuelve solo JSON valido.

PREGUNTA DEL USUARIO:
{pregunta_limpia}

HISTORIAL RECIENTE:
{historial_limpio or "Sin historial reciente."}

PERFIL DEL USUARIO:
{contexto_limpio or "Sin perfil disponible."}

Estructura obligatoria:
{{
  "tipo_operacion": "consulta_documental, reformulacion, historial o fuera_ambito",
  "consulta_normalizada": "consulta clara y enriquecida para busqueda semantica",
  "depende_historial": false,
  "formato_respuesta": "normal, tabla, lista, pasos o resumen",
  "palabras_clave": ["termino importante 1", "termino importante 2"],
  "filtros_sugeridos": {{}}
}}

Reglas:
- Si el usuario pide resumir, aclarar, hacer tabla, hacer lista o cambiar formato de una respuesta anterior, usa tipo_operacion reformulacion y depende_historial true.
- Si la pregunta solo pide formato o estilo, por ejemplo "dame una tabla", "muestrame en lista", "hazlo paso a paso" o "resumelo", siempre usa tipo_operacion reformulacion y depende_historial true.
- Si la pregunta incluye formato y tambien un tema documental claro, por ejemplo "dame una tabla sobre evaluacion del SGA", usa consulta_documental.
- Si pregunta por mensajes anteriores de la conversacion, usa tipo_operacion historial.
- Si consulta documentos, procesos, reglamentos, matricula, evaluacion, aula virtual, asistencia, becas, ayudas economicas, beneficios, tramites o SGA UTEQ, usa consulta_documental.
- Si la pregunta es una consulta documental corta o ambigua y depende del historial, marca depende_historial true.
- Cuando depende_historial sea true, consulta_normalizada debe reconstruir la consulta completa usando el tema del historial reciente. No devuelvas frases genericas como "requisitos que debo cumplir" o "documentos necesarios" sin el tema anterior.
- Ejemplo: si el historial trata de ayudas economicas y el usuario dice "dame los requisitos que debo cumplir", consulta_normalizada debe ser similar a "requisitos que debe cumplir un estudiante para acceder a ayudas economicas del SGA UTEQ".
- Normaliza sinonimos en consulta_normalizada. Por ejemplo: beneficios estudiantiles, becas, apoyo financiero o estipendio pueden relacionarse con ayudas economicas.
- No inventes filtros. Usa filtros_sugeridos solo si la pregunta o el perfil los indican claramente.
- No agregues texto fuera del JSON.
"""

    resultado = consultar_qwen(prompt)
    data = extraer_json_interpretacion(resultado.get("respuesta", ""))
    interpretacion = normalizar_interpretacion(data, pregunta_limpia)
    interpretacion["modelo"] = resultado.get("modelo")
    return interpretacion


def interpretacion_fallback(pregunta, formato_respuesta="normal"):
    return normalizar_interpretacion(
        {
            "tipo_operacion": "consulta_documental",
            "consulta_normalizada": pregunta,
            "formato_respuesta": formato_respuesta,
            "palabras_clave": [],
            "filtros_sugeridos": {},
        },
        pregunta,
    )
