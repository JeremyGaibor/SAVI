from django.urls import path

from . import views

urlpatterns = [  
    path("chatbot/", views.chatbot, name="chatbot"),
    path("chroma_dump.html", views.ver_chroma_dump, name="ver_chroma_dump"),
    path("api/legibilidad/", views.api_legibilidad, name="api_legibilidad"),

    # APIs de integracion para el grupo externo de documentos.
    path("api/integracion/documentos/analizar/", views.api_analizar_documento, name="api_integracion_analizar_documento"),
    path("api/integracion/documentos/guardar-chroma/", views.api_procesar_documento, name="api_integracion_guardar_chroma"),

    # Rutas historicas conservadas como alias.
    path("api/documentos/procesar/", views.api_procesar_documento, name="api_procesar_documento"),
    path("api/ia/buscar/", views.api_buscar_fragmentos, name="api_buscar_fragmentos"),
    path("chat/buscar/", views.api_buscar_fragmentos, name="chat_buscar_fragmentos"),
    path("api/ia/consulta/", views.api_consulta_ia, name="api_consulta_ia"),
    path("api/documentos/analizar/", views.api_analizar_documento, name="api_analizar_documento"),
    path("api/documentos/extraer-texto/", views.api_extraer_texto_documento, name="api_extraer_texto_documento"),
]
