from .contexto_usuario import (
    es_rol_estudiante,
    limpiar_texto_contexto,
    obtener_tipo_estudiante,
)

WEB_PERFIL_PREGUNTA_KEY = "bety_ai_pregunta_pendiente"
WEB_PERFIL_CAMPO_KEY = "bety_ai_campo_pendiente"
WEB_PERFIL_CAMPOS_REQUERIDOS = ["rol", "facultad", "carrera"]


def limpiar_pendiente_perfil_web(request):
    request.session.pop(WEB_PERFIL_PREGUNTA_KEY, None)
    request.session.pop(WEB_PERFIL_CAMPO_KEY, None)
    request.session.modified = True


def obtener_siguiente_campo_perfil_web(perfil):
    if not isinstance(perfil, dict):
        perfil = {}

    if not perfil.get("rol"):
        return "rol"

    if es_rol_estudiante(perfil) and not obtener_tipo_estudiante(perfil):
        return "tipo_estudiante"

    for campo in WEB_PERFIL_CAMPOS_REQUERIDOS:
        if not perfil.get(campo):
            return campo
    return None


def pregunta_campo_perfil_web(campo, pregunta_original="", perfil=None, reintento=False):
    perfil = perfil if isinstance(perfil, dict) else {}
    detalle_consulta = limpiar_texto_contexto(pregunta_original, 120)
    sufijo_consulta = f" sobre \"{detalle_consulta}\"" if detalle_consulta else ""

    preguntas = {
        "rol": (
            f"Antes de responderte{sufijo_consulta}, necesito ubicarte un poco: "
            "¿eres estudiante, docente, aspirante o visitante externo?"
        ),
        "facultad": (
            f"Perfecto, ya sé que eres {perfil.get('rol', 'usuario')}. "
            "¿De qué facultad o área quieres que hablemos? Si es algo general, dime general."
        ),
        "tipo_estudiante": (
            "Para ubicar mejor la informacion del SGA, eres estudiante de pregrado o de posgrado?"
        ),
        "carrera": (
            "¿Y sobre qué carrera sería? Si no aplica o quieres una respuesta general, dime general."
        ),
        "nivel": "¿En qué nivel o semestre estás?",
        "periodo_academico": "¿Cuál es tu periodo académico?",
    }
    pregunta = preguntas.get(campo, "Dame ese dato para continuar.")
    if reintento:
        return f"No logré identificar esa respuesta. {pregunta}"
    return pregunta
