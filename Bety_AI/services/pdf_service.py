import fitz


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

    for indice, pagina in enumerate(documento, start=1):
        texto = pagina.get_text("text") or ""
        texto = texto.strip()
        caracteres = len(texto)

        if caracteres >= 100:
            estado = "OK"
        elif caracteres > 0:
            estado = "POCO_TEXTO"
        else:
            estado = "SIN_TEXTO"

        analisis_paginas.append({
            "pagina": indice,
            "caracteres": caracteres,
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

    requiere_revision = paginas_sin_texto > 0 or paginas_con_poco_texto > 0

    return {
        "texto_total": texto_total,
        "paginas_texto": paginas_texto,
        "total_paginas": total_paginas,
        "caracteres_extraidos": len(texto_total.strip()),
        "paginas_con_texto": paginas_con_texto,
        "paginas_sin_texto": paginas_sin_texto,
        "paginas_con_poco_texto": paginas_con_poco_texto,
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
            "caracteres_extraidos": 0,
            "calidad_extraccion": "ERROR",
            "analisis_paginas": [],
            "mensaje": f"No se pudo analizar el documento: {exc}",
        }


def dividir_texto_en_fragmentos(texto, max_caracteres=1200):
    """
    Divide el texto en fragmentos simples.
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