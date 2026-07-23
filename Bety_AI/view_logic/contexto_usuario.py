import json
import re
import unicodedata


def normalizar_texto(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    return texto.lower().strip()


def limpiar_texto_contexto(valor, limite=500):
    texto = str(valor or "").strip()
    texto = re.sub(r"[\r\n\t]+", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto[:limite]


def normalizar_lista_contexto(valor, limite_items=12):
    if not isinstance(valor, list):
        return ""

    items = []
    for item in valor[:limite_items]:
        texto = limpiar_texto_contexto(item, 120)
        if texto:
            items.append(texto)

    return ", ".join(items)


def es_perfil_estudiante(perfil):
    if not isinstance(perfil, dict):
        return False

    return normalizar_texto(perfil.get("perfil") or perfil.get("usuario")) == "estudiante"


def obtener_tipo_estudiante(contexto):
    if not isinstance(contexto, dict):
        return ""

    for campo in [
        "tipo_estudiante",
        "tipo_estudio",
        "nivel_formacion",
        "nivel_academico",
        "formacion",
    ]:
        valor = limpiar_texto_contexto(contexto.get(campo), 200)
        if valor:
            return valor

    return ""


def perfil_estudiante_requiere_tipo(perfil):
    return es_perfil_estudiante(perfil) and not obtener_tipo_estudiante(perfil)


def obtener_contexto_usuario_sga(data):
    contexto = data.get("contexto_sga") or data.get("usuario_sga")
    if contexto is None:
        usuario = data.get("usuario")
        if isinstance(usuario, dict):
            contexto = usuario
        elif any(campo in data for campo in ["perfil", "nombre", "facultad", "carrera"]):
            contexto = data
        else:
            contexto = usuario

    if isinstance(contexto, str) and contexto.strip():
        try:
            contexto = json.loads(contexto)
        except json.JSONDecodeError:
            contexto = {}

    if not isinstance(contexto, dict):
        return {}

    campos_texto = [
        "perfil",
        "nombre",
        "edad",
        "sexo",
        "facultad",
        "tipo_estudiante",
        "periodo_academico",
        "carrera",
        "nivel",
        "titulo",
    ]

    perfil = {}
    for campo in campos_texto:
        valor = limpiar_texto_contexto(contexto.get(campo), 200)
        if valor:
            perfil[campo] = valor

    if not perfil.get("perfil") and normalizar_texto(contexto.get("usuario")) in {
        "estudiante",
        "docente",
        "aspirante",
    }:
        perfil["perfil"] = limpiar_texto_contexto(contexto.get("usuario"), 200)

    tipo_estudiante = obtener_tipo_estudiante(contexto)
    if tipo_estudiante:
        perfil["tipo_estudiante"] = tipo_estudiante

    materias = normalizar_lista_contexto(contexto.get("materias"))
    if materias:
        perfil["materias"] = materias

    materias_docente = normalizar_lista_contexto(contexto.get("materias_que_da"))
    if materias_docente:
        perfil["materias_que_da"] = materias_docente

    return perfil


def construir_contexto_usuario_prompt(perfil):
    if not perfil:
        return (
            "No hay perfil SGA recibido. Responde de forma general si no hay datos del usuario; "
            "no pidas varios datos personales en una sola respuesta."
        )

    etiquetas = {
        "perfil": "Perfil",
        "nombre": "Nombre",
        "edad": "Edad",
        "sexo": "Sexo",
        "facultad": "Facultad",
        "tipo_estudiante": "Tipo de estudiante",
        "periodo_academico": "Periodo academico",
        "carrera": "Carrera",
        "nivel": "Nivel",
        "titulo": "Titulo",
        "materias": "Materias",
        "materias_que_da": "Materias que imparte",
    }

    lineas = []
    for campo, etiqueta in etiquetas.items():
        valor = perfil.get(campo)
        if valor:
            lineas.append(f"- {etiqueta}: {valor}")

    return "\n".join(lineas)
