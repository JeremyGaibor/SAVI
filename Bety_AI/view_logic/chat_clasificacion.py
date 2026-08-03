import re

from .contexto_usuario import normalizar_texto


def es_consulta_ambito_bety(pregunta):
    texto = normalizar_texto(pregunta)

    palabras_ambito = [
        "sga",
        "uteq",
        "documento",
        "pdf",
        "tramite",
        "tramites",
    ]

    return any(palabra in texto for palabra in palabras_ambito)


def es_pregunta_identidad(pregunta):
    """
    Responde preguntas institucionales sin depender de los PDFs.

    Estas consultas no son documentales; si pasan por ChromaDB pueden terminar
    mezclandose con fragmentos irrelevantes.
    """
    texto = normalizar_texto(pregunta)

    patrones = [
        r"\bque eres\b",
        r"\bquien eres\b",
        r"\bcual es tu proposito\b",
        r"\bpara que sirves\b",
        r"\ben que me puedes servir\b",
        r"\ben que puedes ayudar\b",
        r"\bpara que me puedes ayudar\b",
        r"\bque haces\b",
        r"\bcomo ayudas\b",
        r"\bque puedes hacer\b",
        r"\bcual es tu funcion\b",
    ]

    return any(re.search(patron, texto) for patron in patrones)


def es_interaccion_social(pregunta):
    texto = normalizar_texto(pregunta)

    patrones = [
        r"^hola\b",
        r"^buenos dias\b",
        r"^buenas tardes\b",
        r"^buenas noches\b",
        r"\bcomo estas\b",
        r"\bque tal\b",
        r"\bgracias\b",
    ]

    return any(re.search(patron, texto) for patron in patrones)


def pregunta_necesita_perfil_web(pregunta, interpretacion_consulta=None):
    if es_interaccion_social(pregunta) or es_pregunta_identidad(pregunta):
        return False

    if not isinstance(interpretacion_consulta, dict):
        return False

    return interpretacion_consulta.get("tipo_operacion") == "consulta_documental"


def es_pregunta_fuera_ambito(pregunta):
    """
    Detecta preguntas claramente ajenas al alcance documental de Bety-AI.
    """
    texto = normalizar_texto(pregunta)

    if es_consulta_ambito_bety(pregunta):
        return False

    patrones_fuera = [
        r"\b(chiste|cuento|poema|cancion|receta)\b",
        r"\b(futbol|partido|mundial|barcelona|real madrid)\b",
        r"\b(clima|temperatura|lluvia|pronostico)\b",
        r"\b(politica|presidente|elecciones)\b",
        r"\b(amor|novia|novio|relacion)\b",
        r"\b(programa|codigo|python|javascript)\b",
        r"\b(agujero negro|planeta|espacio|universo)\b",
        r"\b(dolar|bitcoin|acciones|inversion)\b",
        r"\b(capital de|capital del|pais|continente|geografia)\b",
    ]

    return any(re.search(patron, texto) for patron in patrones_fuera)
