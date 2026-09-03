import re

from django.core.cache import cache

from .chat_perfil_web import obtener_siguiente_campo_perfil_web, pregunta_campo_perfil_web
from .chat_validacion_perfil import validar_respuesta_campo
from .contexto_usuario import limpiar_texto_contexto, normalizar_texto

CONVERSACION_CACHE_PREFIX = "bety_ai_conversacion:"
# TTL de inactividad: cada guardado (guardar_estado_conversacion) reinicia el
# contador, asi que la sesion expira solo si pasan 30 min sin nuevos turnos.
CONVERSACION_TTL_SEGUNDOS = 60 * 30
MAX_HISTORIAL_CONVERSACION = 20
MAX_HISTORIAL_PROMPT = 4
# Si el usuario falla la validacion del mismo campo mas de esta cantidad de
# veces, se acepta la respuesta tal cual para no dejar la conversacion
# trabada (por ejemplo, si el LLM de validacion esta caido).
MAX_REINTENTOS_CAMPO_PERFIL = 2


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
        "intentos_fallidos_campo": 0,
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
        estado.setdefault("intentos_fallidos_campo", 0)
        return estado

    return crear_estado_conversacion()


def guardar_estado_conversacion(conversation_id, estado):
    if conversation_id:
        cache.set(
            f"{CONVERSACION_CACHE_PREFIX}{conversation_id}",
            estado,
            CONVERSACION_TTL_SEGUNDOS,
        )


def agregar_historial_conversacion(conversation_id, pregunta, respuesta, tipo_respuesta=None):
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

    historial_qa.append({
        "pregunta": pregunta,
        "respuesta": respuesta,
        "tipo_respuesta": tipo_respuesta,
    })
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
        f"Usuario: {item.get('pregunta', '')}\nSAVI: {item.get('respuesta', '')}"
        for item in historial_qa[-MAX_HISTORIAL_PROMPT:]
        if item.get("pregunta") and item.get("respuesta")
    ]

    return "\n\n".join(bloques)


def formatear_historial_conversacion_solo_preguntas(conversation_id):
    """
    Version del historial para el prompt documental (RESPUESTA), sin las
    respuestas anteriores completas. El router (interpretar_consulta_ia)
    sigue usando formatear_historial_conversacion completo -- esta version
    reducida es solo para el prompt que redacta la respuesta final, para
    que el modelo no tenga ahi mismo un texto ya armado de un tema anterior
    para copiar cuando la pregunta nueva es sobre otro tema (confirmado en
    produccion, ver confirmado_historial_domina_sobre_contexto_documental
    en memoria). Mantiene el hilo de que se hablo, sin darle una respuesta
    lista.
    """
    if not conversation_id:
        return ""

    estado = obtener_estado_conversacion(conversation_id)
    historial_qa = estado.get("historial_qa")
    if not isinstance(historial_qa, list) or not historial_qa:
        return ""

    preguntas = [
        f"Usuario: {item.get('pregunta', '')}"
        for item in historial_qa[-MAX_HISTORIAL_PROMPT:]
        if item.get("pregunta")
    ]

    return "\n".join(preguntas)


def es_pregunta_sobre_historial(pregunta):
    texto = normalizar_texto(limpiar_texto_contexto(pregunta, 300))
    patrones = [
        r"\bprimer mensaje\b",
        r"\bprimera pregunta\b",
        r"\bque te envie primero\b",
        r"\bque te pregunte primero\b",
        r"\bque fue lo primero\b",
        r"\bultimo mensaje\b",
        r"\bultima pregunta\b",
        r"\bque te dije antes\b",
        r"\bque te pregunte antes\b",
    ]
    return any(re.search(patron, texto) for patron in patrones)


def responder_pregunta_sobre_historial(conversation_id, pregunta):
    if not conversation_id or not es_pregunta_sobre_historial(pregunta):
        return None

    estado = obtener_estado_conversacion(conversation_id)
    historial_qa = estado.get("historial_qa")
    if not isinstance(historial_qa, list) or not historial_qa:
        return "No tengo mensajes anteriores guardados en esta conversacion."

    texto = normalizar_texto(limpiar_texto_contexto(pregunta, 300))

    if any(patron in texto for patron in ["primer mensaje", "primera pregunta", "primero"]):
        primer_mensaje = limpiar_texto_contexto(historial_qa[0].get("pregunta"), 300)
        if primer_mensaje:
            return f"Tu primer mensaje en esta conversacion fue: \"{primer_mensaje}\"."

    if any(patron in texto for patron in ["ultimo mensaje", "ultima pregunta", "antes"]):
        for item in reversed(historial_qa):
            mensaje = limpiar_texto_contexto(item.get("pregunta"), 300)
            if mensaje:
                return f"Tu mensaje anterior fue: \"{mensaje}\"."

    return "Tengo historial de esta conversacion, pero no pude identificar que mensaje quieres revisar."


def es_solicitud_reformulacion(pregunta):
    texto = normalizar_texto(limpiar_texto_contexto(pregunta, 300))
    patrones = [
        r"\bmas resumido\b",
        r"\bmas resumida\b",
        r"\bmas breve\b",
        r"\bmas corto\b",
        r"\bmas corta\b",
        r"\bresumelo\b",
        r"\bresume\b",
        r"\bresumir\b",
        r"\ben pocas palabras\b",
        r"\bmas claro\b",
        r"\bmas clara\b",
        r"\bexplicalo mejor\b",
        r"\bexplicame mejor\b",
        r"\bmejor explicado\b",
        r"\bmas sencillo\b",
        r"\bmas sencilla\b",
        r"\bdame una tabla\b",
        r"\bmuestrame una tabla\b",
        r"\bmuestrame en tabla\b",
        r"\ben tabla\b",
        r"\btabla\b",
        r"\bdame una lista\b",
        r"\bmuestrame una lista\b",
        r"\bmuestrame en lista\b",
        r"\ben lista\b",
        r"\blista\b",
        r"\bdame el paso a paso\b",
        r"\bhazlo paso a paso\b",
        r"\bpaso a paso\b",
    ]
    return any(re.search(patron, texto) for patron in patrones)


def obtener_ultima_respuesta_conversacion(conversation_id):
    if not conversation_id:
        return ""

    estado = obtener_estado_conversacion(conversation_id)
    historial_qa = estado.get("historial_qa")
    if not isinstance(historial_qa, list):
        return ""

    for item in reversed(historial_qa):
        respuesta = limpiar_texto_contexto(item.get("respuesta"), 3000)
        if respuesta:
            return respuesta

    return ""


def obtener_ultimo_tipo_respuesta_conversacion(conversation_id):
    if not conversation_id:
        return None

    estado = obtener_estado_conversacion(conversation_id)
    historial_qa = estado.get("historial_qa")
    if not isinstance(historial_qa, list):
        return None

    for item in reversed(historial_qa):
        if item.get("respuesta"):
            return item.get("tipo_respuesta")

    return None


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

    respuesta_limpia = limpiar_texto_contexto(respuesta, 200)
    intentos_fallidos = estado.get("intentos_fallidos_campo", 0)
    pregunta_campo_texto = pregunta_campo_perfil_web(campo, pregunta_pendiente, perfil)

    if (
        not validar_respuesta_campo(campo, respuesta_limpia, pregunta_campo_texto)
        and intentos_fallidos < MAX_REINTENTOS_CAMPO_PERFIL
    ):
        estado["intentos_fallidos_campo"] = intentos_fallidos + 1
        guardar_estado_conversacion(conversation_id, estado)
        return {
            "completo": False,
            "pregunta_original": pregunta_pendiente,
            "respuesta": pregunta_campo_perfil_web(campo, pregunta_pendiente, perfil, reintento=True),
            "perfil": perfil,
        }

    estado["intentos_fallidos_campo"] = 0
    perfil[campo] = respuesta_limpia
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
