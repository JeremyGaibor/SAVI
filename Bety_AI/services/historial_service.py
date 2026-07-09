from django.utils import timezone


HISTORIAL_SESION_KEY = "bety_ai_historial"
MAX_INTERACCIONES_HISTORIAL = 20


def obtener_historial_temporal(request):
    """
    Obtiene el historial temporal guardado en la sesion del navegador.
    Este historial no se usa como conocimiento para responder.
    """
    return request.session.get(HISTORIAL_SESION_KEY, [])


def guardar_interaccion_temporal(
    request,
    pregunta,
    respuesta,
    tipo_respuesta,
    modelo=None,
):
    historial = obtener_historial_temporal(request)

    historial.append({
        "pregunta": pregunta,
        "respuesta": respuesta,
        "tipo_respuesta": tipo_respuesta,
        "modelo": modelo,
        "fecha": timezone.now().isoformat(),
    })

    if len(historial) > MAX_INTERACCIONES_HISTORIAL:
        historial = historial[-MAX_INTERACCIONES_HISTORIAL:]

    request.session[HISTORIAL_SESION_KEY] = historial
    request.session.modified = True

    return historial
