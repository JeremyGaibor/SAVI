import re

from app.services.ollama_service import consultar_qwen

from .contexto_usuario import limpiar_texto_contexto, normalizar_texto

_OPCIONES_PERFIL = ["estudiante", "docente", "aspirante", "visitante_externo", "invalido"]
_OPCIONES_TIPO_ESTUDIANTE = ["pregrado", "posgrado", "invalido"]
_OPCIONES_CAMPO_ABIERTO = ["valido", "invalido"]

_RESPUESTAS_GENERICAS_VALIDAS = {"general", "no aplica", "cualquiera", "ninguna", "n/a", "no se"}

_PROMPT_PERFIL = """Un chatbot universitario pregunto: "¿eres estudiante, docente, aspirante o visitante externo?"
El usuario respondio: "{respuesta}"

Clasifica esa respuesta en una sola palabra, EXACTAMENTE una de estas opciones, sin explicaciones ni puntuacion:
estudiante
docente
aspirante
visitante_externo
invalido (usa esta opcion si la respuesta es una broma, texto incoherente, o no corresponde a ninguna de las anteriores)

Responde solo con la palabra."""

_PROMPT_TIPO_ESTUDIANTE = """Un chatbot universitario pregunto: "¿eres estudiante de pregrado o de posgrado?"
El usuario respondio: "{respuesta}"

Clasifica esa respuesta en una sola palabra, EXACTAMENTE una de estas opciones, sin explicaciones ni puntuacion:
pregrado
posgrado
invalido (usa esta opcion si la respuesta es una broma, texto incoherente, o no corresponde a ninguna de las anteriores)

Responde solo con la palabra."""

_PROMPT_CAMPO_ABIERTO = """Un chatbot universitario pregunto: "{pregunta}"
El usuario respondio: "{respuesta}"

Esa respuesta es VALIDA si es un intento serio de nombrar una facultad, area o carrera universitaria
(aunque no sepas si existe exactamente tal cual), o si equivale a decir "general" / "no aplica" / "cualquiera".
Esa respuesta es INVALIDA si es una broma evidente, texto incoherente, insultos, o claramente no responde
la pregunta (por ejemplo: especies, objetos o lugares de fantasia usados como broma).

Responde solo con una palabra: valido o invalido."""


def _clasificar_con_llm(prompt, opciones_validas):
    try:
        resultado = consultar_qwen(prompt)
    except Exception:
        return None

    texto = normalizar_texto(resultado.get("respuesta", ""))

    for opcion in sorted(opciones_validas, key=len, reverse=True):
        patron = opcion.replace("_", "[_ ]?")
        if re.search(rf"\b{patron}\b", texto):
            return opcion

    return None


def validar_respuesta_campo(campo, respuesta, pregunta_campo=""):
    """
    Valida con el LLM si la respuesta del usuario tiene sentido para el campo
    de perfil pendiente (perfil/tipo_estudiante/facultad/carrera).

    Ante fallas de conexion con el LLM o respuestas que no se pueden
    clasificar, no se bloquea el flujo (fail-open): solo se rechaza cuando
    el LLM identifica explicitamente la respuesta como "invalido".
    """
    respuesta = limpiar_texto_contexto(respuesta, 200)
    if not respuesta:
        return False

    if campo == "perfil":
        clasificacion = _clasificar_con_llm(_PROMPT_PERFIL.format(respuesta=respuesta), _OPCIONES_PERFIL)
        return clasificacion != "invalido"

    if campo == "tipo_estudiante":
        clasificacion = _clasificar_con_llm(
            _PROMPT_TIPO_ESTUDIANTE.format(respuesta=respuesta), _OPCIONES_TIPO_ESTUDIANTE
        )
        return clasificacion != "invalido"

    if campo in ("facultad", "carrera"):
        if normalizar_texto(respuesta) in _RESPUESTAS_GENERICAS_VALIDAS:
            return True

        clasificacion = _clasificar_con_llm(
            _PROMPT_CAMPO_ABIERTO.format(pregunta=pregunta_campo, respuesta=respuesta),
            _OPCIONES_CAMPO_ABIERTO,
        )
        return clasificacion != "invalido"

    return True
