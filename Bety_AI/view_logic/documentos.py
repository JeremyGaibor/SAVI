import json
import re

from ..services.ollama_service import consultar_qwen
from .chat_respuestas_ia import limpiar_respuesta_ia


def parsear_metadata_formulario(valor):
    if not valor.strip():
        return {}

    metadata = json.loads(valor)
    if not isinstance(metadata, dict):
        raise ValueError("Los metadatos deben ser un objeto JSON.")

    return metadata


def obtener_valor_request(request, campo, defecto=""):
    valor = request.data.get(campo, defecto)
    if valor is None:
        return defecto
    return valor


def normalizar_booleano(valor, defecto=False):
    if valor in [None, ""]:
        return defecto
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() in {"1", "true", "si", "sí", "yes", "on"}


def normalizar_valor_metadata(valor):
    if isinstance(valor, (dict, list)):
        return json.dumps(valor, ensure_ascii=False)
    if valor is None:
        return ""
    return str(valor)


def obtener_primer_valor_metadata(request, metadata_extra, campos, defecto=""):
    for campo in campos:
        valor = obtener_valor_request(request, campo, None)
        if valor not in [None, ""]:
            return valor

    for campo in campos:
        valor = metadata_extra.get(campo)
        if valor not in [None, ""]:
            return valor

    return defecto


def construir_metadata_documento(request, archivo):
    metadata_json = obtener_valor_request(request, "metadata", "")
    metadata_extra = {}

    if isinstance(metadata_json, dict):
        metadata_extra = metadata_json
    elif str(metadata_json).strip():
        metadata_extra = parsear_metadata_formulario(str(metadata_json))

    nombre_archivo = archivo.name if archivo is not None else obtener_valor_request(request, "nombre_archivo", "")

    perfil = obtener_primer_valor_metadata(request, metadata_extra, ["perfil"])
    periodo = obtener_primer_valor_metadata(request, metadata_extra, ["periodo", "periodo_academico"])

    metadata_base = {
        "accion_chroma": obtener_valor_request(request, "accion_chroma", ""),
        "id_version": str(obtener_valor_request(request, "id_version", "")),
        "uuid_documento": str(obtener_valor_request(request, "uuid_documento", "")),
        "uuid_version": str(obtener_valor_request(request, "uuid_version", "")),
        "id_version_anterior": str(obtener_valor_request(request, "id_version_anterior", "")),
        "uuid_version_anterior": str(obtener_valor_request(request, "uuid_version_anterior", "")),
        "tipo_documento": obtener_valor_request(request, "tipo_documento", "GENERAL"),
        "ambito": obtener_valor_request(request, "ambito", "PUBLICO"),
        "estado_vigencia": obtener_valor_request(request, "estado_vigencia", "VIGENTE"),
        "anio_documento": str(obtener_valor_request(request, "anio_documento", "")),
        "periodo": normalizar_valor_metadata(periodo),
        "perfil": normalizar_valor_metadata(perfil),
        "carrera": obtener_valor_request(request, "carrera", ""),
        "grupo": obtener_valor_request(request, "grupo", ""),
        "tipo_estudio": obtener_valor_request(request, "tipo_estudio", ""),
        "nombre_archivo": nombre_archivo,
        "resumen_documento": obtener_valor_request(request, "resumen_documento", ""),
        "temas_detectados": normalizar_valor_metadata(obtener_valor_request(request, "temas_detectados", "")),
        "advertencias": normalizar_valor_metadata(obtener_valor_request(request, "advertencias", "")),
        "requiere_revision_humana": str(obtener_valor_request(request, "requiere_revision_humana", "")),
    }

    for clave, valor in metadata_extra.items():
        if clave not in {"id_documento", "titulo", "numero_fragmento", "rol", "periodo_academico"}:
            metadata_base[clave] = normalizar_valor_metadata(valor)

    return metadata_base


def obtener_metadata_request(request):
    metadata = obtener_valor_request(request, "metadata", {})
    if isinstance(metadata, dict):
        return metadata
    if str(metadata).strip():
        return parsear_metadata_formulario(str(metadata))
    return {}


def extraer_json_respuesta(respuesta):
    """
    Convierte la respuesta de Qwen a JSON.

    El modelo a veces envuelve el JSON en markdown o agrega texto antes/despues.
    Esta funcion recorta desde la primera llave hasta la ultima para recuperar
    el objeto JSON que espera la pantalla de analisis.
    """
    respuesta = respuesta.strip()
    respuesta = re.sub(r"^```(?:json)?\s*", "", respuesta)
    respuesta = re.sub(r"\s*```$", "", respuesta)

    inicio = respuesta.find("{")
    fin = respuesta.rfind("}")

    if inicio != -1 and fin != -1 and fin > inicio:
        respuesta = respuesta[inicio:fin + 1]

    return json.loads(respuesta)


def generar_feedback_documento(resultado_texto):
    """
    Pide a Qwen un analisis administrativo del PDF.

    Las metricas tecnicas vienen de PyMuPDF y no del modelo. Qwen solo redacta
    resumen, riesgos y recomendacion usando esas metricas y el texto extraido.
    """
    texto_extraido = resultado_texto.get("texto_total", "")
    muestra_texto = texto_extraido[:6000]

    prompt = f"""
Eres Bety-AI y analizas PDFs institucionales antes de que se guarden en una base documental.

Datos tecnicos del PDF:
- Paginas: {resultado_texto.get("total_paginas", 0)}
- Paginas con texto: {resultado_texto.get("paginas_con_texto", 0)}
- Paginas sin texto: {resultado_texto.get("paginas_sin_texto", 0)}
- Paginas con poco texto: {resultado_texto.get("paginas_con_poco_texto", 0)}
- Paginas con imagenes: {resultado_texto.get("paginas_con_imagenes", 0)}
- Porcentaje de paginas con texto: {resultado_texto.get("porcentaje_paginas_con_texto", 0)}%
- Porcentaje de paginas sin texto: {resultado_texto.get("porcentaje_paginas_sin_texto", 0)}%
- Porcentaje de paginas con imagenes: {resultado_texto.get("porcentaje_paginas_con_imagenes", 0)}%
- Composicion estimada de texto: {resultado_texto.get("porcentaje_texto", 0)}%
- Composicion estimada de imagenes: {resultado_texto.get("porcentaje_imagenes", 0)}%
- Imagenes detectadas: {resultado_texto.get("total_imagenes", 0)}
- Caracteres extraidos: {resultado_texto.get("caracteres_extraidos", 0)}
- Requiere revision: {resultado_texto.get("requiere_revision", False)}

Texto extraido:
{muestra_texto}

Devuelve solo JSON valido, sin markdown ni texto adicional, con esta estructura:
{{
  "resumen_contenido": "resumen breve del documento",
  "tipo_contenido_detectado": "tipo probable del documento",
  "calidad_extraccion": "ALTA, MEDIA o BAJA",
  "porcentaje_texto": {resultado_texto.get("porcentaje_texto", 0)},
  "porcentaje_imagenes": {resultado_texto.get("porcentaje_imagenes", 0)},
  "conteo_imagenes": {resultado_texto.get("total_imagenes", 0)},
  "observaciones_calidad": ["observacion 1", "observacion 2"],
  "riesgos": ["riesgo 1"],
  "recomendacion": "APROBAR, REVISAR u OCR_REQUERIDO",
  "motivo_recomendacion": "motivo concreto"
}}

No inventes informacion que no este en el texto o en los datos tecnicos. Copia exactamente los porcentajes y el conteo de imagenes indicados. Si el texto extraido es insuficiente, indicalo en calidad_extraccion y recomendacion.
"""

    try:
        resultado_qwen = consultar_qwen(prompt)
        respuesta_limpia = limpiar_respuesta_ia(resultado_qwen.get("respuesta", ""))

        try:
            analisis = extraer_json_respuesta(respuesta_limpia)
        except Exception:
            analisis = {
                "resumen_contenido": respuesta_limpia,
                "tipo_contenido_detectado": "No determinado",
                "calidad_extraccion": "MEDIA",
                "porcentaje_texto": resultado_texto.get("porcentaje_texto", 0),
                "porcentaje_imagenes": resultado_texto.get("porcentaje_imagenes", 0),
                "conteo_imagenes": resultado_texto.get("total_imagenes", 0),
                "observaciones_calidad": ["Qwen respondio, pero no devolvio JSON valido."],
                "riesgos": [],
                "recomendacion": "REVISAR",
                "motivo_recomendacion": "Revise manualmente el analisis antes de guardar.",
            }

        # Blindamos los numeros tecnicos. Aunque Qwen devuelva otros valores,
        # la respuesta final conserva los porcentajes calculados por Bety-AI.
        analisis["porcentaje_texto"] = resultado_texto.get("porcentaje_texto", 0)
        analisis["porcentaje_imagenes"] = resultado_texto.get("porcentaje_imagenes", 0)
        analisis["conteo_imagenes"] = resultado_texto.get("total_imagenes", 0)

        return {
            "disponible": True,
            "modelo": resultado_qwen.get("modelo"),
            "feedback": respuesta_limpia,
            "analisis": analisis,
        }
    except Exception as exc:
        return {
            "disponible": False,
            "modelo": None,
            "feedback": (
                "No se pudo generar feedback con Qwen. "
                "Revise el texto extraido y las metricas tecnicas antes de decidir."
            ),
            "analisis": {
                "resumen_contenido": "No se pudo generar analisis con IA.",
                "tipo_contenido_detectado": "No determinado",
                "calidad_extraccion": "REVISAR",
                "porcentaje_texto": resultado_texto.get("porcentaje_texto", 0),
                "porcentaje_imagenes": resultado_texto.get("porcentaje_imagenes", 0),
                "conteo_imagenes": resultado_texto.get("total_imagenes", 0),
                "observaciones_calidad": ["Qwen no respondio durante el analisis del PDF."],
                "riesgos": ["El documento no fue evaluado por IA."],
                "recomendacion": "REVISAR",
                "motivo_recomendacion": "Se requiere revision manual antes de guardar.",
            },
            "error": str(exc),
        }


def normalizar_lista_textos(valor):
    if isinstance(valor, list):
        return [str(item).strip() for item in valor if str(item).strip()]

    if isinstance(valor, str) and valor.strip():
        return [valor.strip()]

    return []


def normalizar_interpretacion_documento(data, resultado_texto):
    if not isinstance(data, dict):
        data = {}

    requiere_revision = bool(resultado_texto.get("requiere_revision", False))
    if resultado_texto.get("caracteres_extraidos", 0) < 1000:
        requiere_revision = True

    anio_documento = data.get("anio_documento_sugerido") or None
    try:
        anio_documento = int(anio_documento) if anio_documento else None
    except (TypeError, ValueError):
        anio_documento = None

    return {
        "titulo_sugerido": str(data.get("titulo_sugerido") or "Documento sin titulo").strip(),
        "tipo_documento_sugerido": str(data.get("tipo_documento_sugerido") or "GENERAL").strip().upper(),
        "perfil_sugerido": str(data.get("perfil_sugerido") or "GENERAL").strip().upper(),
        "carrera_sugerida": str(data.get("carrera_sugerida") or "GENERAL").strip().upper(),
        "tipo_estudio_sugerido": str(data.get("tipo_estudio_sugerido") or "GENERAL").strip().upper(),
        "ambito_sugerido": str(data.get("ambito_sugerido") or "ACADEMICO").strip().upper(),
        "anio_documento_sugerido": anio_documento,
        "estado_vigencia_sugerido": str(data.get("estado_vigencia_sugerido") or "VIGENTE").strip().upper(),
        "resumen": str(data.get("resumen") or "No se pudo generar un resumen confiable del documento.").strip(),
        "temas_detectados": normalizar_lista_textos(data.get("temas_detectados")),
        "advertencias": normalizar_lista_textos(data.get("advertencias")),
        "requiere_revision_humana": bool(data.get("requiere_revision_humana", requiere_revision)),
    }


def generar_interpretacion_documento(resultado_texto, nombre_archivo):
    """
    Interpreta el contenido documental para sugerir metadatos antes de guardar.
    """
    texto_extraido = resultado_texto.get("texto_total", "")
    muestra_texto = texto_extraido[:9000]

    prompt = f"""
Eres Bety-AI y ayudas a clasificar documentos institucionales de la UTEQ antes de guardarlos.

Analiza el texto extraido del PDF y devuelve solo JSON valido, sin markdown ni explicaciones.

Nombre del archivo: {nombre_archivo}

Metricas tecnicas:
- Paginas: {resultado_texto.get("total_paginas", 0)}
- Caracteres extraidos: {resultado_texto.get("caracteres_extraidos", 0)}
- Paginas sin texto: {resultado_texto.get("paginas_sin_texto", 0)}
- Paginas con poco texto: {resultado_texto.get("paginas_con_poco_texto", 0)}
- Requiere revision tecnica: {resultado_texto.get("requiere_revision", False)}

Texto extraido:
{muestra_texto}

Estructura obligatoria:
{{
  "titulo_sugerido": "titulo claro y especifico del documento",
  "tipo_documento_sugerido": "MATRICULA, EVALUACION, AULA_VIRTUAL, CARNET, AYUDA_ECONOMICA, REGLAMENTO, MANUAL, PROCEDIMIENTO, GENERAL u otro tipo breve",
  "perfil_sugerido": "ESTUDIANTE, DOCENTE, ADMINISTRATIVO, ASPIRANTE, GENERAL u otro perfil breve",
  "carrera_sugerida": "GENERAL o carrera especifica si el documento la menciona claramente",
  "tipo_estudio_sugerido": "GRADO, NIVELACION, POSGRADO, GENERAL u otro tipo breve",
  "ambito_sugerido": "ACADEMICO, ADMINISTRATIVO, FINANCIERO, BIENESTAR, GENERAL u otro ambito breve",
  "anio_documento_sugerido": 2026,
  "estado_vigencia_sugerido": "VIGENTE, NO_VIGENTE, BORRADOR, DESCONOCIDO",
  "resumen": "resumen concreto del documento en 2 a 4 frases",
  "temas_detectados": ["tema 1", "tema 2"],
  "advertencias": ["advertencia si aplica"],
  "requiere_revision_humana": true
}}

Reglas:
- No inventes datos no presentes en el texto.
- Si no puedes determinar un campo, usa GENERAL, DESCONOCIDO o null segun corresponda.
- Marca requiere_revision_humana en true si el texto es insuficiente, el documento parece de prueba, hay paginas sin texto, o faltan datos criticos.
- Los temas deben ser utiles para busqueda documental posterior.
"""

    try:
        resultado_qwen = consultar_qwen(prompt)
        respuesta_limpia = limpiar_respuesta_ia(resultado_qwen.get("respuesta", ""))

        try:
            data = extraer_json_respuesta(respuesta_limpia)
        except Exception:
            data = {
                "titulo_sugerido": nombre_archivo,
                "tipo_documento_sugerido": "GENERAL",
                "perfil_sugerido": "GENERAL",
                "carrera_sugerida": "GENERAL",
                "tipo_estudio_sugerido": "GENERAL",
                "ambito_sugerido": "GENERAL",
                "anio_documento_sugerido": None,
                "estado_vigencia_sugerido": "DESCONOCIDO",
                "resumen": respuesta_limpia or "Qwen respondio, pero no devolvio JSON valido.",
                "temas_detectados": [],
                "advertencias": ["La IA no devolvio una interpretacion JSON valida."],
                "requiere_revision_humana": True,
            }

        return {
            "disponible": True,
            "modelo": resultado_qwen.get("modelo"),
            "interpretacion": normalizar_interpretacion_documento(data, resultado_texto),
        }
    except Exception as exc:
        return {
            "disponible": False,
            "modelo": None,
            "interpretacion": normalizar_interpretacion_documento(
                {
                    "titulo_sugerido": nombre_archivo,
                    "advertencias": [f"No se pudo consultar Qwen para interpretar el documento: {exc}"],
                    "requiere_revision_humana": True,
                },
                resultado_texto,
            ),
            "error": str(exc),
        }
