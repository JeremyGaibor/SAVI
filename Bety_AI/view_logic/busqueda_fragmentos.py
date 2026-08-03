import re

from ..services.chroma_service import buscar_fragmentos
from .contexto_usuario import limpiar_texto_contexto, normalizar_texto


FILTROS_DOCUMENTALES_PERMITIDOS = [
    "ambito",
    "estado_vigencia",
    "perfil",
    "facultad",
    "carrera",
    "tipo_documento",
    "id_documento",
    "grupo",
    "periodo",
    "periodo_academico",
    "tipo_periodo",
    "perfiles",
    "grupos",
    "tipos_periodo",
]


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
        filtros.update(normalizar_filtros_documentales(filtros_recibidos))

    filtros.update(normalizar_filtros_documentales(data))
    return filtros


def normalizar_filtros_documentales(data):
    if not isinstance(data, dict):
        return {}

    filtros = {}
    for campo in FILTROS_DOCUMENTALES_PERMITIDOS:
        valor = data.get(campo)
        if valor not in [None, ""]:
            filtros[campo] = valor

    filtros_limpios = {}
    for clave, valor in filtros.items():
        if valor in [None, ""]:
            continue
        if clave == "rol":
            continue
        if clave in {"tipo_estudio", "tipo_estudiante"}:
            continue
        if clave == "acceso":
            clave = "ambito"
        clave = normalizar_clave_filtro_documental(clave)
        if not clave:
            continue
        if clave == "ambito" and isinstance(valor, str):
            valor = valor.upper()
        filtros_limpios[clave] = valor

    return filtros_limpios


def normalizar_clave_filtro_documental(clave):
    equivalencias = {
        "perfil": "perfiles",
        "facultad": "grupos",
        "grupo": "grupos",
        "periodo": "tipos_periodo",
        "periodo_academico": "tipos_periodo",
        "tipo_periodo": "tipos_periodo",
    }
    if clave == "carrera":
        return ""
    return equivalencias.get(clave, clave)


def valor_filtro_general(valor):
    texto = normalizar_texto(valor)
    return texto in {"", "general", "todos", "todas", "no aplica", "n/a", "ninguna"}


def normalizar_valor_filtro_perfil(valor):
    if valor_filtro_general(valor):
        return ""
    return limpiar_texto_contexto(valor, 120)


def normalizar_tipo_estudio(valor):
    texto = normalizar_texto(valor)

    if texto in {"pregrado", "grado"}:
        return "pregrado grado"
    if texto in {"posgrado", "postgrado"}:
        return "posgrado postgrado"

    return limpiar_texto_contexto(valor, 120)


def tipo_estudiante_perfil(perfil):
    if not isinstance(perfil, dict):
        return ""

    texto = normalizar_texto(
        perfil.get("tipo_estudiante")
        or perfil.get("tipo_estudio")
        or perfil.get("nivel_formacion")
    )

    if texto in {"pregrado", "grado"}:
        return "pregrado"
    if texto in {"posgrado", "postgrado"}:
        return "posgrado"

    return ""


def construir_filtros_desde_perfil(perfil):
    if not isinstance(perfil, dict):
        return {}

    filtros = {}
    perfil_documental = normalizar_valor_filtro_perfil(perfil.get("perfil"))
    if perfil_documental:
        filtros["perfiles"] = perfil_documental

    grupo_documental = normalizar_valor_filtro_perfil(
        perfil.get("grupo") or perfil.get("facultad")
    )
    if grupo_documental:
        filtros["grupos"] = grupo_documental

    periodo_documental = normalizar_valor_filtro_perfil(
        perfil.get("tipo_periodo")
        or perfil.get("periodo_academico")
        or perfil.get("periodo")
    )
    if periodo_documental:
        filtros["tipos_periodo"] = periodo_documental

    return filtros


def construir_pregunta_busqueda_con_perfil(pregunta, perfil):
    pregunta_busqueda = limpiar_texto_contexto(pregunta, 500)
    if not isinstance(perfil, dict):
        return pregunta_busqueda

    if not consulta_usa_tipo_estudiante(pregunta_busqueda):
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


def es_pregunta_seguimiento(pregunta):
    texto = normalizar_texto(pregunta)
    if detectar_tema_consulta(texto):
        return False

    patrones = [
        r"\bpaso a paso\b",
        r"\bdetallamelo\b",
        r"\bdetalle\b",
        r"\bexplicame\b",
        r"\bampliame\b",
        r"\bamplia\b",
        r"\bprofundiza\b",
        r"\bmas contexto\b",
        r"\bmas informacion\b",
        r"\bmas especifico\b",
        r"\bmas especifica\b",
        r"\bmas resumido\b",
        r"\bmas resumida\b",
        r"\bmas breve\b",
        r"\bmas corto\b",
        r"\bmas corta\b",
        r"\bresumelo\b",
        r"\bresume\b",
        r"\bresumir\b",
        r"\bresumen\b",
        r"\ben pocas palabras\b",
        r"\bmas claro\b",
        r"\bmas clara\b",
        r"\bexplicalo mejor\b",
        r"\bexplicame mejor\b",
        r"\bmejor\b",
        r"\beso\b",
        r"\besto\b",
        r"\blo anterior\b",
        r"\bdel tema\b",
        r"\beste proceso\b",
        r"\bese proceso\b",
        r"\bcomo hago\b",
        r"\bcomo seria\b",
        r"\bque sigue\b",
        r"\by despues\b",
    ]
    return any(re.search(patron, texto) for patron in patrones)


def construir_pregunta_busqueda_contextual(pregunta, pregunta_anterior=""):
    pregunta_limpia = limpiar_texto_contexto(pregunta, 500)
    anterior_limpia = limpiar_texto_contexto(pregunta_anterior, 300)

    if not pregunta_limpia or detectar_tema_consulta(pregunta_limpia):
        return pregunta_limpia

    if not anterior_limpia or not es_pregunta_seguimiento(pregunta_limpia):
        return pregunta_limpia

    return f"{anterior_limpia} {pregunta_limpia}".strip()


def consulta_usa_tipo_estudiante(pregunta):
    texto = normalizar_texto(pregunta)
    tema = detectar_tema_consulta(pregunta)

    if tema == "matricula":
        return True

    palabras_nivel_estudio = [
        "admision",
        "admisiones",
        "ayudante",
        "ayudantia",
        "ayudantias",
        "catedra",
        "inscripcion",
        "inscribirme",
        "remuneracion",
        "estipendio",
        "requisito",
        "requisitos",
    ]
    return any(palabra in texto for palabra in palabras_nivel_estudio)


def contiene_palabra(texto, palabra):
    return re.search(rf"\b{re.escape(palabra)}\b", texto) is not None


def menciona_pregrado(texto):
    return contiene_palabra(texto, "pregrado") or contiene_palabra(texto, "grado")


def menciona_posgrado(texto):
    return contiene_palabra(texto, "posgrado") or contiene_palabra(texto, "postgrado")


def fragmento_contrario_a_tipo_estudiante(fragmento, tipo_estudiante):
    metadata = fragmento.get("metadata") or {}
    texto = normalizar_texto(
        " ".join(
            [
                metadata.get("titulo", ""),
                metadata.get("tipo_estudio", ""),
                metadata.get("resumen_documento", ""),
                fragmento.get("contenido", "")[:1200],
            ]
        )
    )

    if tipo_estudiante == "pregrado":
        return menciona_posgrado(texto) and not menciona_pregrado(texto)
    if tipo_estudiante == "posgrado":
        return menciona_pregrado(texto) and not menciona_posgrado(texto)

    return False


def filtrar_fragmentos_por_tipo_estudiante(pregunta, perfil, fragmentos):
    if not fragmentos or not consulta_usa_tipo_estudiante(pregunta):
        return fragmentos

    texto_pregunta = normalizar_texto(pregunta)
    if menciona_pregrado(texto_pregunta) and menciona_posgrado(texto_pregunta):
        return fragmentos

    tipo_estudiante = tipo_estudiante_perfil(perfil)
    if not tipo_estudiante:
        return fragmentos

    return [
        fragmento
        for fragmento in fragmentos
        if not fragmento_contrario_a_tipo_estudiante(fragmento, tipo_estudiante)
    ]


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
    campos_relajables = [
        "tipo_estudio",
        "facultad",
        "carrera",
        "perfil",
        "grupos",
        "tipos_periodo",
        "perfiles",
    ]

    for campo in campos_relajables:
        if campo in filtros_base:
            relajado = dict(filtros_base)
            relajado.pop(campo, None)
            if relajado and relajado not in variantes:
                variantes.append(relajado)

    for campos_a_quitar in [
        ["facultad", "carrera"],
        ["tipo_estudio", "facultad", "carrera"],
        ["facultad", "carrera", "perfil"],
        ["grupos", "tipos_periodo"],
        ["grupos", "tipos_periodo", "perfiles"],
    ]:
        relajado = dict(filtros_base)
        for campo in campos_a_quitar:
            relajado.pop(campo, None)
        if relajado and relajado not in variantes:
            variantes.append(relajado)

    if {} not in variantes:
        variantes.append({})

    return variantes


def detectar_tema_consulta(pregunta):
    texto = normalizar_texto(pregunta)

    if any(palabra in texto for palabra in ["matricula", "matriculacion", "matricular"]):
        if not any(palabra in texto for palabra in [
            "ayuda economica",
            "ayudas economicas",
            "economica",
            "economicas",
            "beca",
            "becas",
            "ayudantia",
            "ayudantias",
        ]):
            return "matricula"

    if any(palabra in texto for palabra in [
        "ayuda economica",
        "ayudas economicas",
        "ayudantia economica",
        "ayudantias economicas",
        "ayudantia",
        "ayudantias",
        "beca",
        "becas",
    ]):
        return "ayudas_economicas"

    if "aula virtual" in texto or texto.strip() == "aula":
        return "aula_virtual"

    if any(palabra in texto for palabra in [
        "evaluacion",
        "evaluaciones",
        "evalua",
        "evaluar",
        "calificacion",
        "calificaciones",
    ]):
        return "evaluacion"

    if any(palabra in texto for palabra in [
        "inasistencia",
        "inasistencias",
        "asistencia",
        "asistencias",
        "justificar",
        "justificacion",
        "atraso",
        "atrasos",
        "llegue tarde",
        "llegar tarde",
    ]):
        return "asistencia"

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
        if any(palabra in texto_revision for palabra in [
            "ayuda economica",
            "ayudas economicas",
            "beca",
            "becas",
            "modelo evaluativo",
            "evaluacion",
            "evaluaciones",
            "calificacion",
            "calificaciones",
            "gestion en el aula",
            "trabajo autonomo",
            "examen final",
        ]):
            return False
        return any(palabra in texto_revision for palabra in [
            "matriculacion",
            "matricular",
            "proceso de matricula",
            "proceso para la matricula",
            "matricula en linea",
            "matricula academica",
            "periodo de matricula",
        ])

    if tema == "ayudas_economicas":
        return any(palabra in texto_revision for palabra in [
            "ayuda economica",
            "ayudas economicas",
            "ayudantia economica",
            "ayudantias economicas",
            "ayudantia",
            "ayudantias",
            "beca",
            "becas",
        ])

    if tema == "aula_virtual":
        return "aula virtual" in texto_revision

    if tema == "evaluacion":
        return any(palabra in texto_revision for palabra in [
            "evaluacion",
            "evaluaciones",
            "evalua",
            "evaluar",
            "calificacion",
        ])

    if tema == "asistencia":
        return any(palabra in texto_revision for palabra in [
            "inasistencia",
            "inasistencias",
            "asistencia",
            "asistencias",
            "justificar",
            "justificacion",
            "atraso",
            "atrasos",
            "llegue tarde",
            "llegar tarde",
        ])

    return True


def buscar_fragmentos_con_fallback(pregunta, filtros, total_resultados=3):
    ultimo_error = None
    tema = detectar_tema_consulta(pregunta)

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

        if tema:
            fragmentos = [
                fragmento
                for fragmento in fragmentos
                if fragmento_pertenece_tema(fragmento, tema)
            ]

        if fragmentos and fragmentos_suficientes_para_responder(fragmentos):
            return fragmentos, filtros_actuales

        if fragmentos and not filtros_actuales and not tema:
            return fragmentos, filtros_actuales

    if ultimo_error:
        raise ultimo_error

    return [], {}
