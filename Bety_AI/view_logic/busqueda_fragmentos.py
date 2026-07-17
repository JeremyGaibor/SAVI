from ..services.chroma_service import buscar_fragmentos
from .contexto_usuario import limpiar_texto_contexto, normalizar_texto


def fragmentos_suficientes_para_responder(fragmentos):
    if not fragmentos:
        return False

    mejor_coincidencia = max(
        float(fragmento.get("coincidencia_lexica") or 0)
        for fragmento in fragmentos
    )

    return mejor_coincidencia > 0


def extraer_filtros_consulta(data):
    filtros = {}
    filtros_recibidos = data.get("filtros")

    if isinstance(filtros_recibidos, dict):
        filtros.update(filtros_recibidos)

    campos_permitidos = [
        "ambito",
        "estado_vigencia",
        "rol",
        "facultad",
        "carrera",
        "tipo_documento",
        "id_documento",
        "grupo",
    ]

    for campo in campos_permitidos:
        valor = data.get(campo)
        if valor not in [None, ""]:
            filtros[campo] = valor

    filtros_limpios = {}
    for clave, valor in filtros.items():
        if valor in [None, ""]:
            continue
        if clave in {"tipo_estudio", "tipo_estudiante"}:
            continue
        if clave == "acceso":
            clave = "ambito"
        if clave == "ambito" and isinstance(valor, str):
            valor = valor.upper()
        filtros_limpios[clave] = valor

    return filtros_limpios


def valor_filtro_general(valor):
    texto = normalizar_texto(valor)
    return texto in {"", "general", "todos", "todas", "no aplica", "n/a", "ninguna"}


def normalizar_valor_filtro_perfil(valor):
    if valor_filtro_general(valor):
        return ""
    return limpiar_texto_contexto(valor, 120).upper()


def normalizar_tipo_estudio(valor):
    texto = normalizar_texto(valor)

    if texto in {"pregrado", "grado"}:
        return "pregrado grado"
    if texto in {"posgrado", "postgrado"}:
        return "posgrado postgrado"

    return limpiar_texto_contexto(valor, 120)


def construir_filtros_desde_perfil(perfil):
    if not isinstance(perfil, dict):
        return {}

    filtros = {}
    for campo in ["rol", "facultad", "carrera"]:
        valor = normalizar_valor_filtro_perfil(perfil.get(campo))
        if valor:
            filtros[campo] = valor

    return filtros


def construir_pregunta_busqueda_con_perfil(pregunta, perfil):
    pregunta_busqueda = limpiar_texto_contexto(pregunta, 500)
    if not isinstance(perfil, dict):
        return pregunta_busqueda

    tipo_estudiante = normalizar_tipo_estudio(
        perfil.get("tipo_estudiante")
        or perfil.get("tipo_estudio")
        or perfil.get("nivel_formacion")
    )
    if not tipo_estudiante:
        return pregunta_busqueda

    texto_pregunta = normalizar_texto(pregunta_busqueda)
    if any(palabra in texto_pregunta for palabra in normalizar_texto(tipo_estudiante).split()):
        return pregunta_busqueda

    return f"{pregunta_busqueda} {tipo_estudiante}".strip()


def combinar_filtros_consulta_y_perfil(filtros_consulta, perfil):
    filtros = {}
    if isinstance(filtros_consulta, dict):
        filtros.update(filtros_consulta)

    for clave, valor in construir_filtros_desde_perfil(perfil).items():
        filtros.setdefault(clave, valor)

    return filtros


def relajar_filtros_busqueda(filtros):
    if not filtros:
        return [{}]

    filtros_base = dict(filtros)
    variantes = [filtros_base]

    for campo in ["tipo_estudio", "facultad", "carrera", "rol"]:
        if campo in filtros_base:
            relajado = dict(filtros_base)
            relajado.pop(campo, None)
            if relajado and relajado not in variantes:
                variantes.append(relajado)

    if {} not in variantes:
        variantes.append({})

    return variantes


def detectar_tema_consulta(pregunta):
    texto = normalizar_texto(pregunta)

    if any(palabra in texto for palabra in ["matricula", "matriculacion", "matricular"]):
        if not any(palabra in texto for palabra in ["ayuda", "ayudas", "economica", "economicas", "beca", "becas"]):
            return "matricula"

    if any(palabra in texto for palabra in ["ayuda economica", "ayudas economicas", "beca", "becas"]):
        return "ayudas_economicas"

    if "aula virtual" in texto or texto.strip() == "aula":
        return "aula_virtual"

    if any(palabra in texto for palabra in ["evaluacion", "evaluaciones", "evaluar", "calificacion", "calificaciones"]):
        return "evaluacion"

    return ""


def fragmento_pertenece_tema(fragmento, tema):
    if not tema:
        return True

    metadata = fragmento.get("metadata") or {}
    texto_revision = normalizar_texto(
        " ".join(
            [
                metadata.get("titulo", ""),
                metadata.get("tipo_documento", ""),
                metadata.get("resumen_documento", ""),
                fragmento.get("contenido", "")[:500],
            ]
        )
    )

    if tema == "matricula":
        if any(palabra in texto_revision for palabra in ["ayuda economica", "ayudas economicas", "beca", "becas"]):
            return False
        return any(palabra in texto_revision for palabra in ["matricula", "matriculacion", "matricular"])

    if tema == "ayudas_economicas":
        return any(palabra in texto_revision for palabra in ["ayuda economica", "ayudas economicas", "beca", "becas"])

    if tema == "aula_virtual":
        return "aula virtual" in texto_revision

    if tema == "evaluacion":
        return any(palabra in texto_revision for palabra in ["evaluacion", "evaluaciones", "evaluar", "calificacion"])

    return True


def filtrar_fragmentos_por_tema(pregunta, fragmentos):
    tema = detectar_tema_consulta(pregunta)
    if not tema:
        return fragmentos

    return [
        fragmento
        for fragmento in fragmentos
        if fragmento_pertenece_tema(fragmento, tema)
    ]


def buscar_fragmentos_con_fallback(pregunta, filtros, total_resultados=3):
    ultimo_error = None

    for filtros_actuales in relajar_filtros_busqueda(filtros):
        try:
            fragmentos = buscar_fragmentos(
                pregunta=pregunta,
                filtros=filtros_actuales if filtros_actuales else None,
                total_resultados=total_resultados,
            )
        except Exception as exc:
            ultimo_error = exc
            continue

        fragmentos = filtrar_fragmentos_por_tema(pregunta, fragmentos)

        if fragmentos and fragmentos_suficientes_para_responder(fragmentos):
            return fragmentos, filtros_actuales

        if fragmentos and not filtros_actuales:
            return fragmentos, filtros_actuales

    if ultimo_error:
        raise ultimo_error

    return [], {}
