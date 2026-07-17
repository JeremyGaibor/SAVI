import json
import re


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


def obtener_contexto_usuario_sga(data):
    contexto = data.get("contexto_sga") or data.get("usuario_sga") or data.get("usuario")

    if isinstance(contexto, str) and contexto.strip():
        try:
            contexto = json.loads(contexto)
        except json.JSONDecodeError:
            contexto = {}

    if not isinstance(contexto, dict):
        return {}

    campos_texto = [
        "rol",
        "nombre",
        "edad",
        "sexo",
        "facultad",
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
        "rol": "Rol",
        "nombre": "Nombre",
        "edad": "Edad",
        "sexo": "Sexo",
        "facultad": "Facultad",
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
