from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from unittest.mock import patch

from .views import api_procesar_documento
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
