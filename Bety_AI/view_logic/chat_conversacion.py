import re

from django.core.cache import cache

from .chat_perfil_web import obtener_siguiente_campo_perfil_web, pregunta_campo_perfil_web
from .contexto_usuario import limpiar_texto_contexto

CONVERSACION_CACHE_PREFIX = "bety_ai_conversacion:"
CONVERSACION_TTL_SEGUNDOS = 60 * 60 * 6
MAX_HISTORIAL_CONVERSACION = 4


def normalizar_conversation_id(valor):
    texto = limpiar_texto_contexto(valor, 80)
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", texto):
        return ""
    return texto


def crear_estado_conversacion():
    return {
        "perfil_usuario": {},
        "campo_pendiente": None,
        "pregunta_original": None,
        "historial_qa": [],
    }


def obtener_estado_conversacion(conversation_id):
    if not conversation_id:
        return crear_estado_conversacion()

    estado = cache.get(f"{CONVERSACION_CACHE_PREFIX}{conversation_id}")
    if isinstance(estado, dict):
        estado.setdefault("perfil_usuario", {})
        estado.setdefault("campo_pendiente", None)
        estado.setdefault("pregunta_original", None)
        estado.setdefault("historial_qa", [])
        return estado

    return crear_estado_conversacion()


def guardar_estado_conversacion(conversation_id, estado):
    if conversation_id:
        cache.set(
            f"{CONVERSACION_CACHE_PREFIX}{conversation_id}",
            estado,
            CONVERSACION_TTL_SEGUNDOS,
        )


def agregar_historial_conversacion(conversation_id, pregunta, respuesta):
    """
    Guarda el turno en el estado cacheado por conversation_id (no en la sesion
    de Django) porque en el iframe de terceros las cookies de sesion pueden
    no persistir, mientras que conversation_id siempre llega en el body.
    """
    if not conversation_id:
        return

    estado = obtener_estado_conversacion(conversation_id)
    historial_qa = estado.get("historial_qa")
    if not isinstance(historial_qa, list):
        historial_qa = []

    historial_qa.append({"pregunta": pregunta, "respuesta": respuesta})
    estado["historial_qa"] = historial_qa[-MAX_HISTORIAL_CONVERSACION:]
    guardar_estado_conversacion(conversation_id, estado)


def formatear_historial_conversacion(conversation_id):
    if not conversation_id:
        return ""

    estado = obtener_estado_conversacion(conversation_id)
    historial_qa = estado.get("historial_qa")
    if not isinstance(historial_qa, list) or not historial_qa:
        return ""

    bloques = [
        f"Usuario: {item.get('pregunta', '')}\nBety: {item.get('respuesta', '')}"
        for item in historial_qa
        if item.get("pregunta") and item.get("respuesta")
    ]

    return "\n\n".join(bloques)


def obtener_ultima_pregunta_conversacion(conversation_id):
    if not conversation_id:
        return ""

    estado = obtener_estado_conversacion(conversation_id)
    historial_qa = estado.get("historial_qa")
    if not isinstance(historial_qa, list):
        return ""

    for item in reversed(historial_qa):
        pregunta = limpiar_texto_contexto(item.get("pregunta"), 300)
        if pregunta:
            return pregunta

    return ""


def guardar_perfil_sga_conversacion(conversation_id, perfil_sga):
    estado = obtener_estado_conversacion(conversation_id)
    estado["perfil_usuario"] = perfil_sga
    estado["campo_pendiente"] = None
    estado["pregunta_original"] = None
    guardar_estado_conversacion(conversation_id, estado)
    return estado


def guardar_respuesta_campo_conversacion(conversation_id, respuesta):
    estado = obtener_estado_conversacion(conversation_id)
    campo = estado.get("campo_pendiente")
    pregunta_pendiente = estado.get("pregunta_original")

    if not isinstance(campo, str) or not campo or not pregunta_pendiente:
        return None

    perfil = estado.get("perfil_usuario")
    if not isinstance(perfil, dict):
        perfil = {}

    perfil[campo] = limpiar_texto_contexto(respuesta, 200)
    estado["perfil_usuario"] = perfil

    siguiente_campo = obtener_siguiente_campo_perfil_web(perfil)
    if siguiente_campo:
        estado["campo_pendiente"] = siguiente_campo
        guardar_estado_conversacion(conversation_id, estado)
        return {
            "completo": False,
            "pregunta_original": pregunta_pendiente,
            "respuesta": pregunta_campo_perfil_web(
                siguiente_campo,
                pregunta_pendiente,
                perfil,
            ),
            "perfil": perfil,
        }

    estado["campo_pendiente"] = None
    estado["pregunta_original"] = None
    guardar_estado_conversacion(conversation_id, estado)
    return {
        "completo": True,
        "pregunta_original": pregunta_pendiente,
        "perfil": perfil,
    }


def iniciar_recoleccion_perfil_conversacion(conversation_id, pregunta, perfil):
    estado = obtener_estado_conversacion(conversation_id)
    estado["perfil_usuario"] = perfil if isinstance(perfil, dict) else {}
    campo = obtener_siguiente_campo_perfil_web(estado["perfil_usuario"])

    if not campo:
        guardar_estado_conversacion(conversation_id, estado)
        return None

    estado["campo_pendiente"] = campo
    estado["pregunta_original"] = pregunta
    guardar_estado_conversacion(conversation_id, estado)
    return pregunta_campo_perfil_web(campo, pregunta, estado["perfil_usuario"])
