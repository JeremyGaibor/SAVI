from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from unittest.mock import patch

from .views import api_procesar_documento
from .view_logic.busqueda_fragmentos import (
    construir_filtros_desde_perfil,
    construir_pregunta_busqueda_con_perfil,
    extraer_filtros_consulta,
    relajar_filtros_busqueda,
)
from .view_logic.chat_perfil_web import obtener_siguiente_campo_perfil_web
from .view_logic.contexto_usuario import (
    construir_contexto_usuario_prompt,
    obtener_contexto_usuario_sga,
    perfil_estudiante_requiere_tipo,
)
from .services.pdf_service import (
    dividir_documento_en_fragmentos,
    dividir_paginas_en_fragmentos,
    extraer_paginas_desde_texto,
    obtener_modo_fragmentacion,
)


class FragmentacionDocumentoTests(SimpleTestCase):
    def test_extrae_paginas_desde_texto_analizado(self):
        texto = "[Pagina 1]\nContenido uno.\n\n[Pagina 2]\nContenido dos."

        paginas = extraer_paginas_desde_texto(texto)

        self.assertEqual(
            paginas,
            [
                {"pagina": 1, "texto": "Contenido uno."},
                {"pagina": 2, "texto": "Contenido dos."},
            ],
        )

    def test_divide_un_fragmento_por_pagina(self):
        fragmentos = dividir_paginas_en_fragmentos([
            {"pagina": 3, "texto": "Texto de la tercera pagina."},
        ])

        self.assertEqual(len(fragmentos), 1)
        self.assertEqual(fragmentos[0]["pagina_inicio"], 3)
        self.assertEqual(fragmentos[0]["pagina_fin"], 3)
        self.assertIn("Texto de la tercera pagina.", fragmentos[0]["contenido"])

    def test_fallback_por_caracteres_si_no_hay_paginas(self):
        fragmentos, modo = dividir_documento_en_fragmentos(
            "uno\n\ndos",
            paginas_texto=[],
        )

        self.assertEqual(modo, "characters")
        self.assertEqual(fragmentos, [{"contenido": "uno\ndos"}])

    def test_modo_caracteres_lee_tamano_desde_env(self):
        with patch("Bety_AI.services.pdf_service.FRAGMENTATION_MODE", "caracteres1200"):
            self.assertEqual(obtener_modo_fragmentacion(), ("characters", 1200))


class ContextoUsuarioSgaTests(SimpleTestCase):
    def test_estudiante_sga_sin_tipo_requiere_pregrado_o_posgrado(self):
        perfil = obtener_contexto_usuario_sga({
            "usuario": "estudiante",
            "rol": "estudiante",
            "nombre": "Maria",
            "facultad": "Ciencias Informaticas",
            "carrera": "Ingenieria en Sistemas",
        })

        self.assertTrue(perfil_estudiante_requiere_tipo(perfil))
        self.assertEqual(obtener_siguiente_campo_perfil_web(perfil), "tipo_estudiante")

    def test_docente_sga_no_requiere_tipo_estudiante(self):
        perfil = obtener_contexto_usuario_sga({
            "usuario": {
                "rol": "docente",
                "nombre": "Carlos",
                "facultad": "Ciencias Informaticas",
                "materias_que_da": ["Programacion"],
            }
        })

        self.assertFalse(perfil_estudiante_requiere_tipo(perfil))
        self.assertNotEqual(obtener_siguiente_campo_perfil_web(perfil), "tipo_estudiante")

    def test_tipo_estudiante_llega_al_prompt_y_a_filtros(self):
        perfil = obtener_contexto_usuario_sga({
            "usuario": {
                "rol": "estudiante",
                "tipo_estudio": "Pregrado",
                "facultad": "Ciencias Informaticas",
                "carrera": "Ingenieria en Sistemas",
            }
        })

        prompt = construir_contexto_usuario_prompt(perfil)
        filtros = construir_filtros_desde_perfil(perfil)

        self.assertFalse(perfil_estudiante_requiere_tipo(perfil))
        self.assertIn("- Tipo de estudiante: Pregrado", prompt)
        self.assertNotIn("tipo_estudio", filtros)
        self.assertIn(
            "pregrado",
            construir_pregunta_busqueda_con_perfil("como puedo matricularme", perfil),
        )

    def test_tipo_estudiante_pregrado_no_se_usa_como_filtro_duro(self):
        filtros = extraer_filtros_consulta({"tipo_estudiante": "Pregrado"})

        self.assertNotIn("tipo_estudio", filtros)

    def test_tipo_estudiante_se_agrega_a_la_busqueda_sin_importar_mayusculas(self):
        pregunta = construir_pregunta_busqueda_con_perfil(
            "como puedo matricularme",
            {"rol": "estudiante", "tipo_estudiante": "PREGRADO"},
        )

        self.assertIn("pregrado", pregunta.lower())
        self.assertIn("grado", pregunta.lower())

    def test_tipo_estudiante_no_se_agrega_a_temas_no_relacionados(self):
        pregunta = construir_pregunta_busqueda_con_perfil(
            "como ingreso al aula virtual",
            {"rol": "estudiante", "tipo_estudiante": "PREGRADO"},
        )

        self.assertEqual(pregunta, "como ingreso al aula virtual")

    def test_fallback_relaja_tipo_estudio_si_no_hay_resultados(self):
        variantes = relajar_filtros_busqueda({
            "tipo_estudio": "GRADO",
            "rol": "ESTUDIANTE",
        })

        self.assertIn({"rol": "ESTUDIANTE"}, variantes)

    def test_fallback_prueba_rol_sin_facultad_ni_carrera(self):
        variantes = relajar_filtros_busqueda({
            "rol": "ESTUDIANTE",
            "facultad": "FACULTAD DE CIENCIAS INFORMATICAS",
            "carrera": "INGENIERIA EN SISTEMAS",
        })

        self.assertIn({"rol": "ESTUDIANTE"}, variantes)


class ProcesarDocumentoChromaTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    @patch("Bety_AI.views.guardar_fragmentos_documento", return_value=1)
    @patch("Bety_AI.views.eliminar_documento_chroma")
    @patch("Bety_AI.views.eliminar_version_chroma")
    @patch(
        "Bety_AI.views.dividir_documento_en_fragmentos",
        return_value=([{"contenido": "fragmento nuevo"}], "characters"),
    )
    def test_reemplaza_version_vigente_por_uuid_anterior(
        self,
        dividir_mock,
        eliminar_version_mock,
        eliminar_documento_mock,
        guardar_mock,
    ):
        request = self.factory.post(
            "/api/integracion/documentos/guardar-chroma/",
            {
                "accion_chroma": "reemplazar_version_vigente",
                "id_documento": "123",
                "id_version": "45",
                "uuid_documento": "uuid-del-documento",
                "uuid_version": "uuid-version-nueva",
                "id_version_anterior": "44",
                "uuid_version_anterior": "uuid-version-anterior",
                "reemplazar_existente": True,
                "texto_extraido": "Texto suficientemente largo para superar el minimo de caracteres. " * 3,
                "metadata": {
                    "numero_version": "3",
                    "numero_version_anterior": "2",
                },
            },
            format="json",
        )

        response = api_procesar_documento(request)

        self.assertEqual(response.status_code, 200)
        eliminar_version_mock.assert_called_once_with("uuid-version-anterior")
        eliminar_documento_mock.assert_not_called()
        guardar_mock.assert_called_once()
        metadata_base = guardar_mock.call_args.kwargs["metadata_base"]
        self.assertEqual(metadata_base["uuid_version"], "uuid-version-nueva")
        self.assertEqual(metadata_base["uuid_version_anterior"], "uuid-version-anterior")
        self.assertEqual(metadata_base["numero_version"], "3")
        self.assertTrue(response.data["reemplazo_por_uuid_anterior"])

    @patch("Bety_AI.views.guardar_fragmentos_documento", return_value=1)
    @patch("Bety_AI.views.eliminar_documento_chroma")
    @patch("Bety_AI.views.eliminar_version_chroma")
    @patch(
        "Bety_AI.views.dividir_documento_en_fragmentos",
        return_value=([{"contenido": "fragmento nuevo"}], "characters"),
    )
    def test_mantiene_reemplazo_legacy_por_id_documento(
        self,
        dividir_mock,
        eliminar_version_mock,
        eliminar_documento_mock,
        guardar_mock,
    ):
        request = self.factory.post(
            "/api/integracion/documentos/guardar-chroma/",
            {
                "id_documento": "DOC-123",
                "texto_extraido": "Texto suficientemente largo para superar el minimo de caracteres. " * 3,
            },
            format="json",
        )

        response = api_procesar_documento(request)

        self.assertEqual(response.status_code, 200)
        eliminar_documento_mock.assert_called_once_with("DOC-123")
        eliminar_version_mock.assert_not_called()
        self.assertEqual(guardar_mock.call_args.kwargs["titulo"], "Documento DOC-123")
