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


def normalizar_confianza(valor):
    try:
        confianza = float(valor)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, confianza))


def normalizar_interpretacion(data, pregunta):
    if not isinstance(data, dict):
        data = {}

    pregunta_limpia = limpiar_texto_contexto(pregunta, 500)
    consulta_normalizada_bruta = limpiar_texto_contexto(data.get("consulta_normalizada"), 600)
    consulta_normalizada = consulta_normalizada_bruta or pregunta_limpia
    palabras_clave = normalizar_lista_texto(data.get("palabras_clave"))

    # pregunta_limpia va primero siempre. consulta_normalizada solo se agrega
    # aparte si el router devolvio algo distinto de la pregunta -- si vino
    # vacia y cayo al fallback (arriba), ya esta cubierta por pregunta_limpia
    # y agregarla de nuevo duplicaria el texto completo de la pregunta dentro
    # de consulta_busqueda (bug real: pasaba el 100% de las veces que el
    # router no devolvia consulta_normalizada, incluida interpretacion_fallback).
    partes_busqueda = [pregunta_limpia]
    if consulta_normalizada_bruta and consulta_normalizada_bruta != pregunta_limpia:
        partes_busqueda.append(consulta_normalizada_bruta)
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
        "incluye_saludo": bool(data.get("incluye_saludo", False)),
        "confianza": normalizar_confianza(data.get("confianza")),
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
Eres el router de intenciones de Bety-AI, un asistente documental del SGA UTEQ.

No respondas al usuario. Devuelve solo JSON valido.

PREGUNTA DEL USUARIO:
{pregunta_limpia}

HISTORIAL RECIENTE:
{historial_limpio or "Sin historial reciente."}

PERFIL DEL USUARIO:
{contexto_limpio or "Sin perfil disponible."}

Bety-AI resuelve un mensaje de una de estas formas, cada una cubre una necesidad distinta:

- consulta_documental: busca en la base documental del SGA UTEQ (procesos, tramites, reglamentos, matricula, evaluacion, aula virtual y cualquier informacion institucional disponible) y responde con eso.
- reformulacion: reutiliza la respuesta que ya se dio en esta misma conversacion y solo le cambia el formato o nivel de detalle (tabla, lista, pasos, resumen, mas breve, mas claro), sin buscar informacion nueva. Solo aplica si ya existe una respuesta previa sobre la que trabajar.
- historial: recupera o cita algo que se dijo antes en esta misma conversacion.
- identidad: se presenta como Bety-AI y explica que hace y como puede ayudar.
- saludo: sostiene una interaccion social (saludar, despedirse, agradecer) que, leida completa, no pide informacion ni ayuda concreta.
- fuera_ambito: el mensaje no tiene relacion alguna con el SGA UTEQ ni con ninguna capacidad anterior.

Para elegir, identifica la necesidad real y dominante del mensaje completo, no solo su apertura o su tono. Un mensaje puede abrir con un saludo y aun asi tener una necesidad real de informacion: "Hola, tienes la guia para ayudantes de catedra?" es consulta_documental, porque pide informacion concreta; el saludo ahi es solo cortesia de apertura, no la intencion dominante. Reserva saludo para mensajes que, leidos completos, no piden nada mas que eso. El mismo criterio aplica a identidad, historial y reformulacion cuando vienen acompañados de una cortesia de apertura.

Estructura obligatoria:
{{
  "tipo_operacion": "consulta_documental, reformulacion, historial, saludo, identidad o fuera_ambito",
  "consulta_normalizada": "consulta clara y enriquecida para busqueda semantica, solo sobre el tema/proceso/documento consultado",
  "depende_historial": false,
  "incluye_saludo": false,
  "formato_respuesta": "normal, tabla, lista, pasos o resumen",
  "palabras_clave": ["termino importante 1", "termino importante 2"],
  "filtros_sugeridos": {{}},
  "confianza": 0.0
}}

Notas de los campos:
- incluye_saludo: true si el mensaje abre con un saludo o cortesia, sin importar el tipo_operacion elegido; permite que la respuesta final abra con un saludo natural antes de resolver la necesidad real.
- depende_historial: true si para entender o resolver el mensaje hace falta el tema o la respuesta de un turno anterior de esta conversacion (tipico en reformulacion, o en consultas cortas/ambiguas que retoman un tema ya hablado). Cuando sea true, consulta_normalizada debe reconstruir la consulta completa usando el tema del historial reciente, no frases genericas como "requisitos que debo cumplir" sin ese tema.
- consulta_normalizada: describe UNICAMENTE el tema, proceso o documento que se busca. No incluyas ahi datos del PERFIL DEL USUARIO (facultad, carrera, rol, nivel de estudio) como texto descriptivo -- por ejemplo, evita frases como "para estudiantes de la Facultad de Software". El perfil se usa aparte para filtrar resultados; repetirlo dentro del texto de busqueda semantica diluye la relevancia. Normaliza sinonimos y expresiones equivalentes segun el historial reciente y la pregunta.
- filtros_sugeridos: solo si la pregunta o el perfil los indican claramente en relacion al tema buscado. No inventes filtros.
- confianza: que tan seguro estas de tu eleccion de tipo_operacion, de 0 (muy incierto) a 1 (muy seguro).

No agregues texto fuera del JSON.
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
