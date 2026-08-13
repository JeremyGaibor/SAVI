import re

from ..services.ollama_service import consultar_qwen

# Etiquetas internas que _construir_contexto_documental (views.py) usa para
# armar el bloque [FUENTE N] que recibe el LLM. La regla 6 del prompt
# documental le prohibe reproducirlas, pero el modelo a veces las copia
# igual (confirmado en produccion, ver pending_alucinacion_inventario_
# documentos en memoria) -- este es el backstop deterministico. Se excluye
# "Documento" a proposito: el titulo del documento no es informacion
# interna sensible como el resto.
_ETIQUETAS_METADATA_INTERNA = (
    "ID documento",
    "Tipo",
    "Vigencia",
    "Año",
    "Periodo",
    "Perfil",
    "Grupo",
    "Nivel académico detectado",
)

_MARCADOR_LISTA = r"(?:[-*•]|\d+[.)])"

# Anclado a inicio de linea (con viñeta/numeracion opcional) y al texto
# exacto de la etiqueta seguido de ":" -- no borra prosa que solo mencione
# estas palabras (ej. "la vigencia del documento es de dos años").
_PATRON_LINEA_METADATA_INTERNA = re.compile(
    r"(?im)^[ \t]*(?:" + _MARCADOR_LISTA + r"[ \t]*)?(?:"
    + "|".join(re.escape(etiqueta) for etiqueta in _ETIQUETAS_METADATA_INTERNA)
    + r")[ \t]*:[ \t]*.*$\n?"
)

_PATRON_MARCADOR_FUENTE_INTERNO = re.compile(
    r"(?im)^[ \t]*\[FUENTE[ \t]*\d+\][ \t]*$\n?"
)

# "Fragmento:" solo se borra si queda sola en su linea (asi la usa
# _construir_contexto_documental, como encabezado antes del contenido) --
# si el modelo la usa seguida de texto en la misma linea, no es el leak.
_PATRON_FRAGMENTO_VACIO = re.compile(
    r"(?im)^[ \t]*(?:" + _MARCADOR_LISTA + r"[ \t]*)?Fragmento[ \t]*:[ \t]*$\n?"
)

_PATRON_VINETA_HUERFANA = re.compile(
    r"(?m)^[ \t]*" + _MARCADOR_LISTA + r"[ \t]*$\n?"
)


def _limpiar_metadata_interna_filtrada(respuesta):
    respuesta = _PATRON_MARCADOR_FUENTE_INTERNO.sub("", respuesta)
    respuesta = _PATRON_FRAGMENTO_VACIO.sub("", respuesta)
    respuesta = _PATRON_LINEA_METADATA_INTERNA.sub("", respuesta)
    respuesta = _PATRON_VINETA_HUERFANA.sub("", respuesta)
    return re.sub(r"\n{3,}", "\n\n", respuesta)


def limpiar_respuesta_ia(respuesta):
    """
    Evita exponer citas tipo "Fuentes: Fuente 1" aunque el modelo las agregue.
    """
    respuesta = respuesta.strip()
    # qwen3 puede filtrar su bloque de razonamiento interno aunque se pida
    # think:false. Si aparece, se descarta y solo queda la respuesta final,
    # evitando que se vean 2 respuestas concatenadas.
    respuesta = re.sub(r"(?is)<think>.*?</think>\s*", "", respuesta)
    respuesta = re.sub(r"(?is)^.*?</think>\s*", "", respuesta)
    respuesta = re.sub(
        r"(?im)^\s*(fuentes?|referencias?)\s*:\s*.*$",
        "",
        respuesta,
    )
    respuesta = _limpiar_metadata_interna_filtrada(respuesta)
    return respuesta.strip()


def instrucciones_por_tipo_respuesta(tipo_respuesta):
    if tipo_respuesta == "IDENTIDAD":
        return (
            '- Inicia exactamente con: "Soy Bety, una asistente virtual para el SGA UTEQ."\n'
            "- Luego explica brevemente que ayudas con documentos, matricula, aula virtual, "
            "evaluacion y tramites academicos.\n"
            "- No saludes como si fuera un saludo casual."
        )

    if tipo_respuesta == "SALUDO":
        return (
            "- Saluda de forma amable.\n"
            "- Orienta al usuario a preguntar por documentos o procesos del SGA UTEQ.\n"
            "- No hagas preguntas defensivas sobre la intencion del usuario.\n"
            "- No digas que la consulta esta fuera de alcance."
        )

    if tipo_respuesta == "FUERA_AMBITO":
        return (
            "- Indica que eso no esta en tu base de informacion.\n"
            "- Explica que tu alcance son los documentos y procesos del SGA UTEQ.\n"
            "- Invita al usuario a preguntar por un tema relacionado con el SGA UTEQ.\n"
            "- No pidas perfil, facultad, carrera, nivel ni periodo."
        )

    return "- Responde segun el tipo solicitado sin inventar informacion institucional especifica."


def generar_respuesta_controlada(pregunta, tipo_respuesta, contexto_usuario=""):
    # Usa Qwen para responder consultas no documentales sin consultar ChromaDB.
    prompt = f"""
Eres Bety, una asistente virtual institucional del SGA UTEQ.

El usuario escribio:
{pregunta}

PERFIL DEL USUARIO:
{contexto_usuario or "No hay perfil SGA recibido."}

Tipo de respuesta solicitada: {tipo_respuesta}

Instrucciones generales:
- Responde en espanol claro, breve y natural.
- No inventes informacion institucional especifica.
- Si existe perfil del usuario, puedes usar su nombre, perfil, carrera, nivel o periodo academico para personalizar la respuesta.
- Si el usuario pregunta por sus datos personales, responde unicamente con la informacion disponible en su perfil. No inventes, completes ni deduzcas datos que no esten presentes.
- Nunca reveles datos personales de otra persona (nombres, cedulas, calificaciones, correos, telefonos u otros datos identificables). Si el usuario pide datos de alguien mas, indica que no puedes compartir informacion personal de otras personas.
- Si no existe perfil, no pidas perfil, facultad, carrera, nivel o periodo en bloque; responde de forma general o invita a hacer una consulta sobre documentos del SGA UTEQ.
- No menciones fuentes, IDs ni documentos internos.

Instrucciones especificas para este tipo:
{instrucciones_por_tipo_respuesta(tipo_respuesta)}
"""

    resultado_qwen = consultar_qwen(prompt)
    return {
        "respuesta": limpiar_respuesta_ia(resultado_qwen.get("respuesta", "")),
        "modelo": resultado_qwen.get("modelo"),
    }


def generar_reformulacion_respuesta(respuesta_anterior, instruccion_usuario):
    prompt = f"""
Eres Bety, una asistente virtual institucional del SGA UTEQ.

El usuario pidio esta reformulacion:
{instruccion_usuario}

RESPUESTA ANTERIOR:
{respuesta_anterior}

Instrucciones obligatorias:
- Usa unicamente la RESPUESTA ANTERIOR.
- No agregues informacion nueva.
- No inventes pasos, requisitos, fechas, documentos, lugares, porcentajes ni enlaces.
- Conserva las acciones obligatorias y los datos importantes.
- Si el usuario pide resumen, reduce la extension sin eliminar pasos esenciales.
- Si el usuario pide tabla, convierte la RESPUESTA ANTERIOR a una tabla Markdown usando solo datos presentes ahi.
- Si el usuario pide lista o pasos, reorganiza la RESPUESTA ANTERIOR en ese formato usando solo datos presentes ahi.
- Si no puedes resumir sin perder informacion esencial, conserva la informacion completa pero mas clara.
- Responde en espanol claro y directo.
- No menciones fuentes, IDs ni documentos internos.
"""

    resultado_qwen = consultar_qwen(prompt)
    return {
        "respuesta": limpiar_respuesta_ia(resultado_qwen.get("respuesta", "")),
        "modelo": resultado_qwen.get("modelo"),
    }


def respuesta_servidor_ia_no_disponible():
    return (
        "El servidor de IA no esta disponible en este momento. "
        "Verifique que AWS/Qwen u Ollama esten encendidos e intente nuevamente."
    )
