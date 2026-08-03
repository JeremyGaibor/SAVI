from ..services.ollama_service import consultar_qwen
from .busqueda_fragmentos import normalizar_filtros_documentales
from .chat_conversacion import es_solicitud_reformulacion
from .comun import extraer_json_desde_respuesta_ia
from .contexto_usuario import limpiar_texto_contexto


FORMATOS_RESPUESTA = {"normal", "tabla", "lista", "pasos", "resumen"}
TIPOS_OPERACION = {
    "consulta_documental",
    "reformulacion",
    "historial",
    "saludo",
    "identidad",
    "fuera_ambito",
}


def extraer_json_interpretacion(respuesta):
    return extraer_json_desde_respuesta_ia(respuesta)


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
    return normalizar_filtros_documentales(valor)


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

    tipo_operacion = normalizar_tipo_operacion(data.get("tipo_operacion"))
    es_reformulacion_pura = es_solicitud_reformulacion(pregunta_limpia)
    if tipo_operacion == "reformulacion" and not es_reformulacion_pura:
        tipo_operacion = "consulta_documental"

    return {
        "tipo_operacion": tipo_operacion,
        "consulta_normalizada": consulta_normalizada,
        "consulta_busqueda": limpiar_texto_contexto(consulta_busqueda, 1000),
        "depende_historial": bool(data.get("depende_historial", False)) and es_reformulacion_pura,
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
  "tipo_operacion": "consulta_documental, reformulacion, historial, saludo, identidad o fuera_ambito",
  "consulta_normalizada": "consulta clara y enriquecida para busqueda semantica, solo sobre el tema/proceso/documento consultado",
  "depende_historial": false,
  "formato_respuesta": "normal, tabla, lista, pasos o resumen",
  "palabras_clave": ["termino importante 1", "termino importante 2"],
  "filtros_sugeridos": {{}}
}}

Reglas:
- Si el usuario solo saluda, se despide o agradece sin una consulta documental, usa tipo_operacion saludo.
- Si pregunta quien eres, que eres, que haces, para que sirves o en que puedes ayudar, usa tipo_operacion identidad.
- Si el usuario pide resumir, aclarar, hacer tabla, hacer lista o cambiar formato de una respuesta anterior, usa tipo_operacion reformulacion y depende_historial true.
- Si la pregunta solo pide formato o estilo, por ejemplo "dame una tabla", "muestrame en lista", "hazlo paso a paso" o "resumelo", siempre usa tipo_operacion reformulacion y depende_historial true.
- Si la pregunta incluye formato y tambien un tema documental claro, por ejemplo "dame una tabla sobre evaluacion del SGA", usa consulta_documental.
- Si pregunta por mensajes anteriores de la conversacion, usa tipo_operacion historial.
- Si consulta documentos, procesos, reglamentos, tramites o informacion institucional disponible en la base documental, usa consulta_documental.
- Si la pregunta es una consulta documental corta o ambigua y depende del historial, marca depende_historial true.
- Cuando depende_historial sea true, consulta_normalizada debe reconstruir la consulta completa usando el tema del historial reciente. No devuelvas frases genericas como "requisitos que debo cumplir" o "documentos necesarios" sin el tema anterior.
- Normaliza sinonimos y expresiones equivalentes en consulta_normalizada segun el historial reciente y la pregunta del usuario.
- consulta_normalizada debe describir UNICAMENTE el tema, proceso o documento que se busca. NO incluyas ahi datos del PERFIL DEL USUARIO (facultad, carrera, rol, nivel de estudio) como texto descriptivo -- por ejemplo, evita frases como "para estudiantes de la Facultad de Software" o "como estudiante de la carrera de FCC". El perfil se usa aparte para filtrar resultados; repetirlo dentro del texto de busqueda semantica diluye la relevancia y puede hacer que se encuentren documentos genericos de perfil en vez del documento especifico del tema.
- Si el perfil es relevante para filtrar, indicalo en filtros_sugeridos, nunca como texto dentro de consulta_normalizada.
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
