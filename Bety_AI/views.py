from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from .services.ollama_service import consultar_qwen
from rest_framework import status


from .services.pdf_service import (
    analizar_legibilidad_pdf,
    extraer_texto_pdf,
    dividir_texto_en_fragmentos,
)
from .services.chroma_service import guardar_fragmentos_documento, buscar_fragmentos




@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def api_legibilidad(request):
    archivo = request.FILES.get("archivo")

    if archivo is None:
        return Response(
            {"error": "Debe enviar un archivo PDF en el campo 'archivo'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not archivo.name.lower().endswith(".pdf"):
        return Response(
            {"error": "Solo se permiten archivos PDF."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    resultado = analizar_legibilidad_pdf(archivo)

    return Response(resultado, status=status.HTTP_200_OK)


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def api_procesar_documento(request):
    archivo = request.FILES.get("archivo")

    if archivo is None:
        return Response(
            {"error": "Debe enviar un archivo PDF en el campo 'archivo'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not archivo.name.lower().endswith(".pdf"):
        return Response(
            {"error": "Solo se permiten archivos PDF."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    id_documento = request.POST.get("id_documento")
    titulo = request.POST.get("titulo")
    tipo_documento = request.POST.get("tipo_documento", "GENERAL")
    ambito = request.POST.get("ambito", "PUBLICO")
    estado_vigencia = request.POST.get("estado_vigencia", "VIGENTE")
    anio_documento = request.POST.get("anio_documento", "")
    rol = request.POST.get("rol", "")
    carrera = request.POST.get("carrera", "")
    grupo = request.POST.get("grupo", "")
    tipo_estudio = request.POST.get("tipo_estudio", "")

    if not id_documento:
        return Response(
            {"error": "Debe enviar el campo 'id_documento'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not titulo:
        return Response(
            {"error": "Debe enviar el campo 'titulo'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        resultado_texto = extraer_texto_pdf(archivo)

        texto_total = resultado_texto["texto_total"]
        total_paginas = resultado_texto["total_paginas"]
        caracteres_extraidos = resultado_texto["caracteres_extraidos"]
        paginas_con_texto = resultado_texto["paginas_con_texto"]
        paginas_sin_texto = resultado_texto["paginas_sin_texto"]
        paginas_con_poco_texto = resultado_texto["paginas_con_poco_texto"]
        requiere_revision = resultado_texto["requiere_revision"]
        analisis_paginas = resultado_texto["analisis_paginas"]

        if caracteres_extraidos < 100:
            return Response(
                {
                    "id_documento": id_documento,
                    "titulo": titulo,
                    "estado_procesamiento": "PENDIENTE_OCR",
                    "requiere_ocr": True,
                    "paginas": total_paginas,
                    "caracteres_extraidos": caracteres_extraidos,
                    "fragmentos_generados": 0,
                    "mensaje": "El documento tiene poco o ningún texto seleccionable. Requiere OCR.",
                },
                status=status.HTTP_200_OK,
            )

        fragmentos = dividir_texto_en_fragmentos(texto_total)

        metadata_base = {
            "tipo_documento": tipo_documento,
            "ambito": ambito,
            "estado_vigencia": estado_vigencia,
            "anio_documento": str(anio_documento),
            "rol": rol,
            "carrera": carrera,
            "grupo": grupo,
            "tipo_estudio": tipo_estudio,
            "nombre_archivo": archivo.name,
        }

        total_fragmentos = guardar_fragmentos_documento(
            id_documento=id_documento,
            titulo=titulo,
            fragmentos=fragmentos,
            metadata_base=metadata_base,
        )

        return Response(
            {
                "id_documento": id_documento,
                "titulo": titulo,
                "estado_procesamiento": "PROCESADO",
                "requiere_ocr": False,
                "paginas": total_paginas,
                "caracteres_extraidos": caracteres_extraidos,
                "fragmentos_generados": total_fragmentos,
                "mensaje": "Documento procesado e indexado correctamente en ChromaDB.",
                "paginas_con_texto": paginas_con_texto,
                "paginas_sin_texto": paginas_sin_texto,
                "paginas_con_poco_texto": paginas_con_poco_texto,
                "requiere_revision": requiere_revision,
                "analisis_paginas": analisis_paginas,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as exc:
        return Response(
            {
                "id_documento": id_documento,
                "titulo": titulo,
                "estado_procesamiento": "ERROR",
                "fragmentos_generados": 0,
                "mensaje": f"Ocurrió un error al procesar el documento: {exc}",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
@api_view(["POST"])
def api_buscar_fragmentos(request):
    pregunta = request.data.get("pregunta")

    if not pregunta:
        return Response(
            {"error": "Debe enviar el campo 'pregunta'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    filtros = {}

    ambito = request.data.get("ambito")
    estado_vigencia = request.data.get("estado_vigencia")
    rol = request.data.get("rol")
    carrera = request.data.get("carrera")
    tipo_estudio = request.data.get("tipo_estudio")

    if ambito:
        filtros["ambito"] = ambito

    if estado_vigencia:
        filtros["estado_vigencia"] = estado_vigencia

    if rol:
        filtros["rol"] = rol

    if carrera:
        filtros["carrera"] = carrera

    if tipo_estudio:
        filtros["tipo_estudio"] = tipo_estudio

    fragmentos = buscar_fragmentos(
        pregunta=pregunta,
        filtros=filtros if filtros else None,
        total_resultados=3
    )

    return Response(
        {
            "pregunta": pregunta,
            "fragmentos_encontrados": len(fragmentos),
            "fragmentos": fragmentos,
        },
        status=status.HTTP_200_OK,
    )
@api_view(["POST"])
def api_consulta_ia(request):
    pregunta = request.data.get("pregunta")

    if not pregunta:
        return Response(
            {"error": "Debe enviar el campo 'pregunta'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    filtros = {}

    ambito = request.data.get("ambito")
    estado_vigencia = request.data.get("estado_vigencia")
    rol = request.data.get("rol")
    carrera = request.data.get("carrera")
    tipo_estudio = request.data.get("tipo_estudio")

    if ambito:
        filtros["ambito"] = ambito

    if estado_vigencia:
        filtros["estado_vigencia"] = estado_vigencia

    if rol:
        filtros["rol"] = rol

    if carrera:
        filtros["carrera"] = carrera

    if tipo_estudio:
        filtros["tipo_estudio"] = tipo_estudio

    fragmentos = buscar_fragmentos(
        pregunta=pregunta,
        filtros=filtros if filtros else None,
        total_resultados=3
    )

    if not fragmentos:
        return Response(
            {
                "pregunta": pregunta,
                "tipo_respuesta": "SIN_INFORMACION",
                "respuesta": "No encontré información suficiente en los documentos disponibles para responder esa consulta.",
                "fuentes": [],
            },
            status=status.HTTP_200_OK,
        )

    contexto = ""

    for indice, fragmento in enumerate(fragmentos, start=1):
        metadata = fragmento["metadata"]
        contenido = fragmento["contenido"]

        contexto += f"""
[FUENTE {indice}]
Documento: {metadata.get("titulo", "Sin título")}
ID documento: {metadata.get("id_documento", "")}
Tipo: {metadata.get("tipo_documento", "")}
Vigencia: {metadata.get("estado_vigencia", "")}
Año: {metadata.get("anio_documento", "")}
Fragmento:
{contenido}
"""

    prompt = f"""
Eres Bety-AI, un asistente virtual institucional.

Reglas obligatorias:
1. Responde únicamente con base en el CONTEXTO proporcionado.
2. No inventes información.
3. Si el contexto no alcanza, di que no hay información suficiente.
4. Responde en español claro y directo.
5. No menciones razonamientos internos.
6. Al final, menciona brevemente las fuentes usadas.

CONTEXTO:
{contexto}

PREGUNTA DEL USUARIO:
{pregunta}

RESPUESTA:
"""

    try:
        resultado_qwen = consultar_qwen(prompt)

        fuentes = []

        for fragmento in fragmentos:
            metadata = fragmento["metadata"]
            fuentes.append({
                "id_documento": metadata.get("id_documento"),
                "titulo": metadata.get("titulo"),
                "tipo_documento": metadata.get("tipo_documento"),
                "estado_vigencia": metadata.get("estado_vigencia"),
                "anio_documento": metadata.get("anio_documento"),
                "numero_fragmento": metadata.get("numero_fragmento"),
            })

        return Response(
            {
                "pregunta": pregunta,
                "tipo_respuesta": "RESPUESTA",
                "respuesta": resultado_qwen["respuesta"],
                "modelo": resultado_qwen["modelo"],
                "fragmentos_usados": len(fragmentos),
                "fuentes": fuentes,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as exc:
        return Response(
            {
                "pregunta": pregunta,
                "tipo_respuesta": "ERROR_IA",
                "respuesta": "Ocurrió un error al consultar el modelo de IA.",
                "detalle": str(exc),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def api_extraer_texto_documento(request):
    archivo = request.FILES.get("archivo")

    if archivo is None:
        return Response(
            {"error": "Debe enviar un archivo PDF en el campo 'archivo'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not archivo.name.lower().endswith(".pdf"):
        return Response(
            {"error": "Solo se permiten archivos PDF."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        resultado_texto = extraer_texto_pdf(archivo)

        return Response(
            {
                "nombre_archivo": archivo.name,
                "estado_extraccion": "EXTRAIDO",
                "paginas": resultado_texto["total_paginas"],
                "paginas_con_texto": resultado_texto["paginas_con_texto"],
                "paginas_sin_texto": resultado_texto["paginas_sin_texto"],
                "paginas_con_poco_texto": resultado_texto["paginas_con_poco_texto"],
                "requiere_revision": resultado_texto["requiere_revision"],
                "caracteres_extraidos": resultado_texto["caracteres_extraidos"],
                "analisis_paginas": resultado_texto["analisis_paginas"],
                "texto_extraido": resultado_texto["texto_total"],
                "mensaje": "Texto extraído correctamente. Revise el contenido antes de confirmar el procesamiento.",
            },
            status=status.HTTP_200_OK,
        )

    except Exception as exc:
        return Response(
            {
                "nombre_archivo": archivo.name,
                "estado_extraccion": "ERROR",
                "texto_extraido": "",
                "mensaje": f"No se pudo extraer el texto del documento: {exc}",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )