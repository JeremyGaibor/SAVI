import fitz
import os
import re
from dotenv import load_dotenv


load_dotenv()

FRAGMENTATION_MODE = os.getenv("DOCUMENT_FRAGMENTATION_MODE", "pages").strip().lower()

try:
    FRAGMENT_MAX_CHARACTERS = int(os.getenv("DOCUMENT_FRAGMENT_MAX_CHARACTERS", "1200"))
except (TypeError, ValueError):
    FRAGMENT_MAX_CHARACTERS = 1200


def area_bbox(bbox):
    """
    Calcula el area de un bloque usando su caja (x0, y0, x1, y1).
    PyMuPDF entrega estas cajas para texto e imagenes dentro de cada pagina.
    """
    x0, y0, x1, y1 = bbox
    ancho = max(0, x1 - x0)
    alto = max(0, y1 - y0)
    return ancho * alto


def medir_contenido_pagina(pagina):
    """
    Mide contenido visible de una pagina.

    Usa get_text("dict") porque separa bloques renderizados de texto e imagen.
    Esto evita contar recursos internos del PDF que no necesariamente aparecen
    como imagenes visibles en la pagina.
    """
    datos = pagina.get_text("dict")
    area_texto = 0
    area_imagenes = 0
    imagenes = 0

    for bloque in datos.get("blocks", []):
        tipo = bloque.get("type")
        bbox = bloque.get("bbox", [0, 0, 0, 0])

        if tipo == 0:
            area_texto += area_bbox(bbox)
        elif tipo == 1:
            imagenes += 1
            area_imagenes += area_bbox(bbox)

    area_pagina = pagina.rect.width * pagina.rect.height

    return {
        "imagenes": imagenes,
        "area_texto": min(area_texto, area_pagina),
        "area_imagenes": min(area_imagenes, area_pagina),
    }


def extraer_texto_pdf(archivo_pdf):
    """
    Extrae texto completo de un PDF recibido como archivo.
    También genera un resumen página por página para validar si hubo páginas vacías.
    """
    contenido = archivo_pdf.read()
    documento = fitz.open(stream=contenido, filetype="pdf")

    total_paginas = documento.page_count
    paginas_texto = []
    analisis_paginas = []
    total_imagenes = 0
    area_texto_total = 0
    area_imagenes_total = 0

    # Recorremos cada pagina una vez: extraemos texto, medimos bloques visibles
    # y acumulamos los datos que luego se muestran al administrador.
    for indice, pagina in enumerate(documento, start=1):
        texto = pagina.get_text("text") or ""
        texto = texto.strip()
        caracteres = len(texto)
        medicion_pagina = medir_contenido_pagina(pagina)
        imagenes = medicion_pagina["imagenes"]
        area_texto = medicion_pagina["area_texto"]
        area_imagenes = medicion_pagina["area_imagenes"]
        total_imagenes += imagenes
        area_texto_total += area_texto
        area_imagenes_total += area_imagenes

        if caracteres >= 100:
            estado = "OK"
        elif caracteres > 0:
            estado = "POCO_TEXTO"
        else:
            estado = "SIN_TEXTO"

        area_contenido_pagina = area_texto + area_imagenes

        # Composicion visual de la pagina. Cuando hay texto e imagenes,
        # ambos porcentajes se calculan sobre el area visible y suman 100%.
        if area_contenido_pagina > 0:
            porcentaje_texto_pagina = round((area_texto / area_contenido_pagina) * 100, 2)
            porcentaje_imagenes_pagina = round(100 - porcentaje_texto_pagina, 2)
        elif caracteres > 0:
            porcentaje_texto_pagina = 100
            porcentaje_imagenes_pagina = 0
        else:
            porcentaje_texto_pagina = 0
            porcentaje_imagenes_pagina = 0

        analisis_paginas.append({
            "pagina": indice,
            "caracteres": caracteres,
            "imagenes": imagenes,
            "porcentaje_texto": porcentaje_texto_pagina,
            "porcentaje_imagenes": porcentaje_imagenes_pagina,
            "estado": estado,
        })

        if texto:
            paginas_texto.append({
                "pagina": indice,
                "texto": texto
            })

    documento.close()

    texto_total = "\n\n".join(
        f"[Página {item['pagina']}]\n{item['texto']}"
        for item in paginas_texto
    )

    paginas_con_texto = sum(
        1 for pagina in analisis_paginas
        if pagina["estado"] in ["OK", "POCO_TEXTO"]
    )

    paginas_sin_texto = sum(
        1 for pagina in analisis_paginas
        if pagina["estado"] == "SIN_TEXTO"
    )

    paginas_con_poco_texto = sum(
        1 for pagina in analisis_paginas
        if pagina["estado"] == "POCO_TEXTO"
    )

    paginas_con_imagenes = sum(
        1 for pagina in analisis_paginas
        if pagina["imagenes"] > 0
    )

    if total_paginas > 0:
        porcentaje_paginas_con_texto = round((paginas_con_texto / total_paginas) * 100, 2)
        porcentaje_paginas_sin_texto = round((paginas_sin_texto / total_paginas) * 100, 2)
        porcentaje_paginas_con_imagenes = round((paginas_con_imagenes / total_paginas) * 100, 2)
    else:
        porcentaje_paginas_con_texto = 0
        porcentaje_paginas_sin_texto = 0
        porcentaje_paginas_con_imagenes = 0

    area_contenido_total = area_texto_total + area_imagenes_total

    # Composicion global del documento: texto + imagenes = 100%.
    # Esto no es lo mismo que "porcentaje de paginas con texto/imagenes".
    if area_contenido_total > 0:
        porcentaje_texto = round((area_texto_total / area_contenido_total) * 100, 2)
        porcentaje_imagenes = round(100 - porcentaje_texto, 2)
    elif len(texto_total.strip()) > 0:
        porcentaje_texto = 100
        porcentaje_imagenes = 0
    else:
        porcentaje_texto = 0
        porcentaje_imagenes = 0

    requiere_revision = paginas_sin_texto > 0 or paginas_con_poco_texto > 0

    return {
        "texto_total": texto_total,
        "paginas_texto": paginas_texto,
        "total_paginas": total_paginas,
        "caracteres_extraidos": len(texto_total.strip()),
        "paginas_con_texto": paginas_con_texto,
        "paginas_sin_texto": paginas_sin_texto,
        "paginas_con_poco_texto": paginas_con_poco_texto,
        "paginas_con_imagenes": paginas_con_imagenes,
        "porcentaje_paginas_con_texto": porcentaje_paginas_con_texto,
        "porcentaje_paginas_sin_texto": porcentaje_paginas_sin_texto,
        "porcentaje_paginas_con_imagenes": porcentaje_paginas_con_imagenes,
        "porcentaje_texto": porcentaje_texto,
        "porcentaje_imagenes": porcentaje_imagenes,
        "total_imagenes": total_imagenes,
        "requiere_revision": requiere_revision,
        "analisis_paginas": analisis_paginas,
    }


def analizar_legibilidad_pdf(archivo_pdf):
    """
    Analiza si un PDF tiene texto seleccionable.
    Además valida página por página.
    """
    try:
        resultado = extraer_texto_pdf(archivo_pdf)

        caracteres_extraidos = resultado["caracteres_extraidos"]
        total_paginas = resultado["total_paginas"]
        paginas_con_texto = resultado["paginas_con_texto"]
        paginas_sin_texto = resultado["paginas_sin_texto"]
        paginas_con_poco_texto = resultado["paginas_con_poco_texto"]
        paginas_con_imagenes = resultado["paginas_con_imagenes"]
        porcentaje_paginas_con_texto = resultado["porcentaje_paginas_con_texto"]
        porcentaje_paginas_sin_texto = resultado["porcentaje_paginas_sin_texto"]
        porcentaje_paginas_con_imagenes = resultado["porcentaje_paginas_con_imagenes"]
        porcentaje_texto = resultado["porcentaje_texto"]
        porcentaje_imagenes = resultado["porcentaje_imagenes"]
        total_imagenes = resultado["total_imagenes"]
        requiere_revision = resultado["requiere_revision"]
        analisis_paginas = resultado["analisis_paginas"]

        if caracteres_extraidos >= 1000 and not requiere_revision:
            calidad = "ALTA"
            legible = True
            requiere_ocr = False
            mensaje = "El documento contiene texto seleccionable en todas las páginas analizadas."
        elif caracteres_extraidos >= 100:
            calidad = "MEDIA"
            legible = True
            requiere_ocr = requiere_revision
            mensaje = "El documento contiene texto, pero algunas páginas tienen poco o ningún texto extraíble."
        else:
            calidad = "BAJA"
            legible = False
            requiere_ocr = True
            mensaje = "El documento tiene poco o ningún texto seleccionable. Probablemente requiere OCR."

        return {
            "legible": legible,
            "requiere_ocr": requiere_ocr,
            "requiere_revision": requiere_revision,
            "paginas": total_paginas,
            "paginas_con_texto": paginas_con_texto,
            "paginas_sin_texto": paginas_sin_texto,
            "paginas_con_poco_texto": paginas_con_poco_texto,
            "paginas_con_imagenes": paginas_con_imagenes,
            "porcentaje_paginas_con_texto": porcentaje_paginas_con_texto,
            "porcentaje_paginas_sin_texto": porcentaje_paginas_sin_texto,
            "porcentaje_paginas_con_imagenes": porcentaje_paginas_con_imagenes,
            "porcentaje_texto": porcentaje_texto,
            "porcentaje_imagenes": porcentaje_imagenes,
            "total_imagenes": total_imagenes,
            "caracteres_extraidos": caracteres_extraidos,
            "calidad_extraccion": calidad,
            "analisis_paginas": analisis_paginas,
            "mensaje": mensaje,
        }

    except Exception as exc:
        return {
            "legible": False,
            "requiere_ocr": False,
            "requiere_revision": True,
            "paginas": 0,
            "paginas_con_texto": 0,
            "paginas_sin_texto": 0,
            "paginas_con_poco_texto": 0,
            "paginas_con_imagenes": 0,
            "porcentaje_paginas_con_texto": 0,
            "porcentaje_paginas_sin_texto": 0,
            "porcentaje_paginas_con_imagenes": 0,
            "porcentaje_texto": 0,
            "porcentaje_imagenes": 0,
            "total_imagenes": 0,
            "caracteres_extraidos": 0,
            "calidad_extraccion": "ERROR",
            "analisis_paginas": [],
            "mensaje": f"No se pudo analizar el documento: {exc}",
        }


def dividir_texto_en_fragmentos(texto, max_caracteres=1200):
    """
    Divide el texto en fragmentos simples.

    Se usa antes de guardar en ChromaDB para que cada fragmento tenga
    un tamano manejable durante la busqueda semantica.
    """
    parrafos = [p.strip() for p in texto.split("\n") if p.strip()]

    fragmentos = []
    actual = ""

    for parrafo in parrafos:
        if len(actual) + len(parrafo) + 1 <= max_caracteres:
            actual += "\n" + parrafo if actual else parrafo
        else:
            if actual:
                fragmentos.append(actual.strip())
            actual = parrafo

    if actual:
        fragmentos.append(actual.strip())

    return fragmentos


def obtener_modo_fragmentacion():
    if FRAGMENTATION_MODE in {"pages", "paginas", "pagina"}:
        return "pages", FRAGMENT_MAX_CHARACTERS

    coincidencia_caracteres = re.fullmatch(r"(?:caracteres|characters|chars)(\d+)?", FRAGMENTATION_MODE)
    if coincidencia_caracteres:
        max_caracteres = int(coincidencia_caracteres.group(1) or FRAGMENT_MAX_CHARACTERS)
        return "characters", max_caracteres

    if FRAGMENTATION_MODE in {"characters", "character", "chars", "caracteres", "cantidad"}:
        return "characters", FRAGMENT_MAX_CHARACTERS

    return "pages", FRAGMENT_MAX_CHARACTERS


def extraer_paginas_desde_texto(texto):
    """
    Reconstruye paginas cuando el texto viene de la API de analisis.
    El formato esperado es el que genera extraer_texto_pdf: [Pagina N] + texto.
    """
    patron = re.compile(r"\[(?:P[^\s\]]*|Pagina)\s+(\d+)\]\s*", re.IGNORECASE)
    coincidencias = list(patron.finditer(texto or ""))

    if not coincidencias:
        return []

    paginas = []
    for indice, coincidencia in enumerate(coincidencias):
        inicio = coincidencia.end()
        fin = coincidencias[indice + 1].start() if indice + 1 < len(coincidencias) else len(texto)
        contenido = texto[inicio:fin].strip()

        if contenido:
            paginas.append({
                "pagina": int(coincidencia.group(1)),
                "texto": contenido,
            })

    return paginas


def dividir_paginas_en_fragmentos(paginas_texto):
    fragmentos = []

    for item in paginas_texto:
        texto = str(item.get("texto") or "").strip()
        if not texto:
            continue

        pagina = int(item.get("pagina") or len(fragmentos) + 1)
        fragmentos.append({
            "contenido": f"[PÃ¡gina {pagina}]\n{texto}",
            "pagina_inicio": pagina,
            "pagina_fin": pagina,
        })

    return fragmentos


def dividir_documento_en_fragmentos(texto, paginas_texto=None):
    """
    Divide el documento segun DOCUMENT_FRAGMENTATION_MODE.

    pages: un fragmento por pagina con metadata de pagina.
    characters: fragmentos por cantidad de caracteres, como el flujo anterior.
    """
    modo, max_caracteres = obtener_modo_fragmentacion()

    if modo == "pages":
        paginas = paginas_texto or extraer_paginas_desde_texto(texto)
        fragmentos_por_pagina = dividir_paginas_en_fragmentos(paginas)

        if fragmentos_por_pagina:
            return fragmentos_por_pagina, modo

    fragmentos = [
        {"contenido": fragmento}
        for fragmento in dividir_texto_en_fragmentos(
            texto,
            max_caracteres=max_caracteres,
        )
    ]

    return fragmentos, "characters"
