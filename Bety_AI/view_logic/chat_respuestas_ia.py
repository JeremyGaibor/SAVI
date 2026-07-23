import re

from ..services.ollama_service import consultar_qwen


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
    return respuesta.strip()


def generar_respuesta_controlada(pregunta, tipo_respuesta, contexto_usuario=""):
    """
    Usa Qwen para responder consultas no documentales sin consultar ChromaDB.
    """
    prompt = f"""
Eres Bety, una asistente virtual institucional del SGA UTEQ.

El usuario escribio:
{pregunta}

PERFIL DEL USUARIO:
{contexto_usuario or "No hay perfil SGA recibido."}

Tipo de respuesta solicitada: {tipo_respuesta}

Instrucciones:
- Responde en espanol claro, breve y natural.
- No inventes informacion institucional especifica.
- Si existe perfil del usuario, puedes usar su nombre, perfil, carrera, nivel o periodo academico para personalizar la respuesta.
- Si no existe perfil, no pidas perfil, facultad, carrera, nivel o periodo en bloque; responde de forma general o invita a hacer una consulta sobre documentos del SGA UTEQ.
- No menciones fuentes, IDs ni documentos internos.
- Si el tipo es IDENTIDAD, explica que ayudas con documentos del SGA UTEQ, matricula, aula virtual, evaluacion y tramites academicos.
- Si el tipo es SALUDO, saluda de forma amable y orienta al usuario a preguntar por documentos o procesos del SGA UTEQ.
- Si el tipo es FUERA_AMBITO, responde con humor ligero, indicando que eso no esta en tu base de informacion y que tu alcance son los documentos del SGA UTEQ.
- Para FUERA_AMBITO puedes usar una idea parecida a: "¿Y tu para que deseas saber eso?", pero redactala con tus propias palabras.
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
        "El servidor de IA no está disponible en este momento. "
        "Verifique que AWS/Qwen u Ollama estén encendidos e intente nuevamente."
    )

