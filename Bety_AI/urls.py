from django.urls import path

from . import views

urlpatterns = [
    path("api/legibilidad/", views.api_legibilidad, name="api_legibilidad"),
    path("api/documentos/procesar/", views.api_procesar_documento, name="api_procesar_documento"),
    path("api/ia/buscar/", views.api_buscar_fragmentos, name="api_buscar_fragmentos"),
    path("api/ia/consulta/", views.api_consulta_ia, name="api_consulta_ia"),
    path("api/documentos/extraer-texto/", views.api_extraer_texto_documento, name="api_extraer_texto_documento"),
]