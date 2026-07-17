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
- Si existe perfil del usuario, puedes usar su nombre, rol, carrera, nivel o periodo academico para personalizar la respuesta.
- Si no existe perfil, no pidas rol, facultad, carrera, nivel o periodo en bloque; responde de forma general o invita a hacer una consulta sobre documentos del SGA UTEQ.
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


def respuesta_servidor_ia_no_disponible():
    return (
        "El servidor de IA no está disponible en este momento. "
        "Verifique que AWS/Qwen u Ollama estén encendidos e intente nuevamente."
    )


def fragmentos_suficientes_para_responder(fragmentos):
    if not fragmentos:
        return False

    mejor_coincidencia = max(
        float(fragmento.get("coincidencia_lexica") or 0)
        for fragmento in fragmentos
    )

    return mejor_coincidencia > 0


def generar_respuesta_respaldo_fragmentos(fragmentos):
    respuesta = (
        "No pude consultar el modelo de IA en este momento, "
        "pero encontre informacion relacionada en los documentos:\n\n"
    )

    for indice, fragmento in enumerate(fragmentos[:3], start=1):
        metadata = fragmento.get("metadata", {})
        contenido = fragmento.get("contenido", "").strip()
        titulo = metadata.get("titulo", "Documento sin titulo")

        respuesta += f"{indice}. {titulo}\n"
        respuesta += f"{contenido[:650]}...\n\n"

    return respuesta.strip()
