from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory

from unittest.mock import patch

from .views import api_consulta_ia, api_procesar_documento
from .view_logic.busqueda_fragmentos import (
    construir_filtros_desde_perfil,
    construir_pregunta_busqueda_contextual,
    construir_pregunta_busqueda_con_perfil,
    detectar_tema_consulta,
    extraer_filtros_consulta,
    filtrar_fragmentos_por_tipo_estudiante,
    fragmento_pertenece_tema,
    relajar_filtros_busqueda,
)
from .view_logic.interpretacion_consulta import (
    extraer_json_interpretacion,
    normalizar_interpretacion,
)
from .view_logic.chat_perfil_web import obtener_siguiente_campo_perfil_web
from .view_logic.chat_conversacion import (
    agregar_historial_conversacion,
    es_solicitud_reformulacion,
    formatear_historial_conversacion,
    obtener_ultima_respuesta_conversacion,
    responder_pregunta_sobre_historial,
)
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
            "perfil": "estudiante",
            "nombre": "Maria",
            "facultad": "Ciencias Informaticas",
            "carrera": "Ingenieria en Sistemas",
        })

        self.assertTrue(perfil_estudiante_requiere_tipo(perfil))
        self.assertEqual(obtener_siguiente_campo_perfil_web(perfil), "tipo_estudiante")

    def test_docente_sga_no_requiere_tipo_estudiante(self):
        perfil = obtener_contexto_usuario_sga({
            "usuario": {
                "perfil": "docente",
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
                "perfil": "estudiante",
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

    def test_rol_no_se_usa_como_filtro_documental(self):
        filtros = extraer_filtros_consulta({
            "rol": "ESTUDIANTE",
            "filtros": {"rol": "DOCENTE"},
        })

        self.assertEqual(filtros, {})

    def test_tipo_estudiante_se_agrega_a_la_busqueda_sin_importar_mayusculas(self):
        pregunta = construir_pregunta_busqueda_con_perfil(
            "como puedo matricularme",
            {"perfil": "estudiante", "tipo_estudiante": "PREGRADO"},
        )

        self.assertIn("pregrado", pregunta.lower())
        self.assertIn("grado", pregunta.lower())

    def test_tipo_estudiante_no_se_agrega_a_temas_no_relacionados(self):
        pregunta = construir_pregunta_busqueda_con_perfil(
            "como ingreso al aula virtual",
            {"perfil": "estudiante", "tipo_estudiante": "PREGRADO"},
        )

        self.assertEqual(pregunta, "como ingreso al aula virtual")

    def test_fallback_relaja_tipo_estudio_si_no_hay_resultados(self):
        variantes = relajar_filtros_busqueda({
            "tipo_estudio": "GRADO",
            "perfil": "ESTUDIANTE",
        })

        self.assertIn({"perfil": "ESTUDIANTE"}, variantes)

    def test_fallback_prueba_perfil_sin_facultad_ni_carrera(self):
        variantes = relajar_filtros_busqueda({
            "perfil": "ESTUDIANTE",
            "facultad": "FACULTAD DE CIENCIAS INFORMATICAS",
            "carrera": "INGENIERIA EN SISTEMAS",
        })

        self.assertIn({"perfil": "ESTUDIANTE"}, variantes)

    def test_seguimiento_usa_tema_anterior_para_busqueda(self):
        pregunta = construir_pregunta_busqueda_contextual(
            "dame el paso a paso",
            "como puedo matricularme",
        )

        self.assertEqual(pregunta, "como puedo matricularme dame el paso a paso")

    def test_seguimiento_mas_contexto_usa_pregunta_anterior(self):
        pregunta = construir_pregunta_busqueda_contextual(
            "dame mas contexto",
            "cual es el proceso para las ayudantias economicas",
        )

        self.assertEqual(
            pregunta,
            "cual es el proceso para las ayudantias economicas dame mas contexto",
        )
        self.assertEqual(detectar_tema_consulta(pregunta), "ayudas_economicas")

    def test_seguimiento_mas_corto_usa_pregunta_anterior_sin_tema_legacy(self):
        pregunta = construir_pregunta_busqueda_contextual(
            "dame un paso a paso mas corto",
            "como justifico mi inasistencia",
        )

        self.assertEqual(
            pregunta,
            "como justifico mi inasistencia dame un paso a paso mas corto",
        )
        self.assertEqual(detectar_tema_consulta(pregunta), "asistencia")

    def test_resumen_de_matriculacion_mantiene_tema_anterior(self):
        pregunta = construir_pregunta_busqueda_contextual(
            "resumelo",
            "ayudame con el proceso de matriculacion",
        )

        self.assertEqual(
            pregunta,
            "ayudame con el proceso de matriculacion resumelo",
        )
        self.assertEqual(detectar_tema_consulta(pregunta), "matricula")

    def test_mas_resumido_mantiene_tema_anterior(self):
        pregunta = construir_pregunta_busqueda_contextual(
            "mas resumido",
            "como justifico mi inasistencia",
        )

        self.assertEqual(
            pregunta,
            "como justifico mi inasistencia mas resumido",
        )
        self.assertEqual(detectar_tema_consulta(pregunta), "asistencia")

    def test_filtro_matricula_excluye_modelo_evaluativo(self):
        fragmento = {
            "contenido": "El modelo evaluativo tiene GA 35%, TA 35% y EV 30%. En segunda matricula la nota maxima es 7.00.",
            "metadata": {"titulo": "Modelo evaluativo"},
        }

        self.assertFalse(fragmento_pertenece_tema(fragmento, "matricula"))

    def test_cambio_de_tema_no_usa_pregunta_anterior(self):
        pregunta = construir_pregunta_busqueda_contextual(
            "como ingreso al aula virtual",
            "como puedo matricularme",
        )

        self.assertEqual(pregunta, "como ingreso al aula virtual")

    def test_ayudante_de_catedra_respeta_pregrado_del_perfil(self):
        pregunta = construir_pregunta_busqueda_con_perfil(
            "cuanto gano como ayudante de catedra",
            {"perfil": "estudiante", "tipo_estudiante": "Pregrado"},
        )
        fragmentos = [
            {
                "contenido": "El ayudante de catedra de posgrado recibe USD 520.",
                "metadata": {"titulo": "Ayudantes de posgrado"},
                "coincidencia_lexica": 1,
            },
            {
                "contenido": "El ayudante de catedra de pregrado recibe el estipendio establecido.",
                "metadata": {"titulo": "Ayudantes de pregrado"},
                "coincidencia_lexica": 1,
            },
        ]

        filtrados = filtrar_fragmentos_por_tipo_estudiante(
            pregunta,
            {"perfil": "estudiante", "tipo_estudiante": "Pregrado"},
            fragmentos,
        )

        self.assertEqual(len(filtrados), 1)
        self.assertIn("pregrado", filtrados[0]["contenido"])


@override_settings(CACHES={
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-conversacion",
    }
})
class HistorialConversacionTests(SimpleTestCase):
    def test_responde_primer_mensaje_desde_historial(self):
        conversation_id = "convtest01"
        agregar_historial_conversacion(conversation_id, "Hola", "Hola, soy Bety.")
        agregar_historial_conversacion(
            conversation_id,
            "Ayudame con el proceso de matriculacion",
            "Respuesta de matriculacion",
        )

        respuesta = responder_pregunta_sobre_historial(
            conversation_id,
            "Cual fue el primer mensaje que te envie?",
        )

        self.assertEqual(
            respuesta,
            'Tu primer mensaje en esta conversacion fue: "Hola".',
        )

    def test_prompt_usa_ultimos_turnos_sin_perder_primer_mensaje(self):
        conversation_id = "convtest02"
        for indice in range(1, 7):
            agregar_historial_conversacion(
                conversation_id,
                f"Pregunta {indice}",
                f"Respuesta {indice}",
            )

        historial_prompt = formatear_historial_conversacion(conversation_id)
        respuesta = responder_pregunta_sobre_historial(
            conversation_id,
            "cual fue mi primera pregunta?",
        )

        self.assertNotIn("Pregunta 1\n", historial_prompt)
        self.assertIn("Pregunta 6", historial_prompt)
        self.assertEqual(
            respuesta,
            'Tu primer mensaje en esta conversacion fue: "Pregunta 1".',
        )

    def test_detecta_solicitud_de_reformulacion(self):
        self.assertTrue(es_solicitud_reformulacion("mas resumido"))
        self.assertTrue(es_solicitud_reformulacion("explicalo mejor"))
        self.assertTrue(es_solicitud_reformulacion("dame una tabla"))
        self.assertTrue(es_solicitud_reformulacion("muestrame en lista"))
        self.assertFalse(es_solicitud_reformulacion("como justifico mi inasistencia"))

    def test_obtiene_ultima_respuesta_de_conversacion(self):
        conversation_id = "convtest03"
        agregar_historial_conversacion(
            conversation_id,
            "Pregunta inicial",
            "Respuesta inicial",
        )
        agregar_historial_conversacion(
            conversation_id,
            "Otra pregunta",
            "Respuesta mas reciente",
        )

        self.assertEqual(
            obtener_ultima_respuesta_conversacion(conversation_id),
            "Respuesta mas reciente",
        )

    @patch("Bety_AI.views.interpretar_consulta_ia")
    @patch("Bety_AI.views.buscar_fragmentos_con_fallback")
    @patch("Bety_AI.views.guardar_interaccion_temporal", return_value=[])
    @patch("Bety_AI.views.generar_reformulacion_respuesta")
    def test_api_reformula_ultima_respuesta_sin_consultar_chroma(
        self,
        reformular_mock,
        guardar_temporal_mock,
        buscar_mock,
        interpretar_mock,
    ):
        conversation_id = "convtest04"
        agregar_historial_conversacion(
            conversation_id,
            "como justifico mi inasistencia",
            "Para justificar tu inasistencia debes ingresar al SGA y registrar la solicitud.",
        )
        reformular_mock.return_value = {
            "respuesta": "Ingresa al SGA y registra la solicitud de justificacion.",
            "modelo": "qwen-test",
        }
        interpretar_mock.return_value = {
            "tipo_operacion": "reformulacion",
            "consulta_normalizada": "",
            "consulta_busqueda": "",
            "depende_historial": True,
            "formato_respuesta": "resumen",
            "palabras_clave": [],
            "filtros_sugeridos": {},
            "modelo": "qwen-test",
        }

        request = APIRequestFactory().post(
            "/api/chat/",
            {
                "pregunta": "mas resumido",
                "conversation_id": conversation_id,
            },
            format="json",
        )

        response = api_consulta_ia(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["tipo_respuesta"], "REFORMULACION")
        self.assertEqual(
            response.data["respuesta"],
            "Ingresa al SGA y registra la solicitud de justificacion.",
        )
        reformular_mock.assert_called_once()
        guardar_temporal_mock.assert_called_once()
        buscar_mock.assert_not_called()

    def test_normaliza_interpretacion_para_busqueda_enriquecida(self):
        interpretacion = normalizar_interpretacion(
            {
                "tipo_operacion": "consulta_documental",
                "consulta_normalizada": "ayudas economicas becas apoyo financiero",
                "formato_respuesta": "tabla",
                "palabras_clave": ["beneficios estudiantiles", "estipendio"],
            },
            "beneficios para estudiantes",
        )

        self.assertEqual(interpretacion["tipo_operacion"], "consulta_documental")
        self.assertEqual(interpretacion["formato_respuesta"], "tabla")
        self.assertIn("beneficios para estudiantes", interpretacion["consulta_busqueda"])
        self.assertIn("ayudas economicas becas apoyo financiero", interpretacion["consulta_busqueda"])
        self.assertIn("beneficios estudiantiles", interpretacion["consulta_busqueda"])

    def test_extrae_json_interpretacion_desde_markdown(self):
        data = extraer_json_interpretacion(
            '```json\n{"tipo_operacion": "consulta_documental", "formato_respuesta": "lista"}\n```'
        )

        self.assertEqual(data["tipo_operacion"], "consulta_documental")
        self.assertEqual(data["formato_respuesta"], "lista")

    def test_normaliza_interpretacion_de_formato_como_reformulacion(self):
        interpretacion = normalizar_interpretacion(
            {
                "tipo_operacion": "reformulacion",
                "consulta_normalizada": "",
                "depende_historial": True,
                "formato_respuesta": "tabla",
            },
            "dame una tabla",
        )

        self.assertEqual(interpretacion["tipo_operacion"], "reformulacion")
        self.assertTrue(interpretacion["depende_historial"])
        self.assertEqual(interpretacion["formato_respuesta"], "tabla")

    @patch("Bety_AI.views.consultar_qwen")
    @patch("Bety_AI.views.buscar_fragmentos_con_fallback")
    @patch("Bety_AI.views.guardar_interaccion_temporal", return_value=[])
    @patch("Bety_AI.views.interpretar_consulta_ia")
    def test_api_usa_consulta_interpretada_sin_fuera_ambito_manual(
        self,
        interpretar_mock,
        guardar_temporal_mock,
        buscar_mock,
        qwen_mock,
    ):
        interpretar_mock.return_value = {
            "tipo_operacion": "consulta_documental",
            "consulta_normalizada": "ayudas economicas becas beneficios estudiantiles",
            "consulta_busqueda": "programa de becas ayudas economicas becas beneficios estudiantiles",
            "depende_historial": False,
            "formato_respuesta": "normal",
            "palabras_clave": ["becas", "beneficios estudiantiles"],
            "filtros_sugeridos": {},
            "modelo": "qwen-test",
        }
        buscar_mock.return_value = (
            [
                {
                    "contenido": "Las ayudas economicas son beneficios para estudiantes.",
                    "metadata": {
                        "titulo": "Ayudas economicas",
                        "id_documento": "1",
                        "tipo_documento": "AYUDA_ECONOMICA",
                    },
                    "coincidencia_lexica": 1,
                }
            ],
            {},
        )
        qwen_mock.return_value = {
            "respuesta": "Las ayudas economicas son beneficios para estudiantes.",
            "modelo": "qwen-final",
        }

        request = APIRequestFactory().post(
            "/api/chat/",
            {
                "pregunta": "programa de becas",
                "conversation_id": "convtest05",
            },
            format="json",
        )

        response = api_consulta_ia(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["tipo_respuesta"], "RESPUESTA")
        self.assertIn("ayudas economicas", buscar_mock.call_args.kwargs["pregunta"])
        guardar_temporal_mock.assert_called_once()

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
                "perfil": "ESTUDIANTE",
                "periodo": "2026-S1",
                "grupo": "POSGRADO",
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
        self.assertEqual(metadata_base["perfil"], "ESTUDIANTE")
        self.assertEqual(metadata_base["periodo"], "2026-S1")
        self.assertEqual(metadata_base["grupo"], "POSGRADO")
        self.assertNotIn("rol", metadata_base)
        self.assertTrue(response.data["reemplazo_por_uuid_anterior"])

    @patch("Bety_AI.views.guardar_fragmentos_documento", return_value=1)
    @patch("Bety_AI.views.eliminar_documento_chroma")
    @patch("Bety_AI.views.eliminar_version_chroma")
    @patch(
        "Bety_AI.views.dividir_documento_en_fragmentos",
        return_value=([{"contenido": "fragmento nuevo"}], "characters"),
    )
    def test_ignora_rol_en_metadata_documental(
        self,
        dividir_mock,
        eliminar_version_mock,
        eliminar_documento_mock,
        guardar_mock,
    ):
        request = self.factory.post(
            "/api/integracion/documentos/guardar-chroma/",
            {
                "id_documento": "DOC-ROL",
                "rol": "ESTUDIANTE",
                "texto_extraido": "Texto suficientemente largo para superar el minimo de caracteres. " * 3,
                "metadata": {
                    "rol": "DOCENTE",
                },
            },
            format="json",
        )

        response = api_procesar_documento(request)

        self.assertEqual(response.status_code, 200)
        metadata_base = guardar_mock.call_args.kwargs["metadata_base"]
        self.assertEqual(metadata_base["perfil"], "")
        self.assertNotIn("rol", metadata_base)

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
