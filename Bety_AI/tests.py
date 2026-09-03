import importlib
import os

import requests
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory

from unittest.mock import Mock, patch

from .views import (
    _obtener_usuario_sga_por_sessionid,
    _construir_fuentes_respuesta,
    _construir_prompt_documental,
    _construir_pregunta_busqueda,
    _construir_respuesta_inventario_documentos,
    _describir_filtros_relajados,
    _debe_reformular,
    _obtener_token_api_sga,
    api_actualizar_link_documento,
    api_consulta_ia,
    api_procesar_documento,
)
from .view_logic import busqueda_fragmentos as busqueda_fragmentos_module
from .view_logic.busqueda_fragmentos import (
    calcular_penalizacion_nivel_contrario,
    combinar_filtros_consulta_y_perfil,
    construir_filtros_desde_perfil,
    construir_pregunta_busqueda_contextual,
    construir_pregunta_busqueda_con_perfil,
    detectar_tema_consulta,
    extraer_filtros_consulta,
    filtrar_fragmentos_confiables,
    filtrar_fragmentos_por_tipo_estudiante,
    fragmento_pertinente_consulta,
    fragmento_pertenece_tema,
    nivel_academico_fragmento,
    buscar_fragmentos_con_fallback,
    relajar_filtros_busqueda,
)
from .services import chroma_service
from .services.chroma_service import (
    calcular_score_ranking,
    metadata_cumple_filtros_flexibles,
)
from .view_logic.interpretacion_consulta import (
    extraer_json_interpretacion,
    interpretacion_fallback,
    normalizar_interpretacion,
)
from .view_logic.chat_perfil_web import obtener_siguiente_campo_perfil_web
from .view_logic.chat_clasificacion import (
    es_pregunta_fuera_ambito,
    es_pregunta_inventario_documentos,
    pregunta_necesita_perfil_web,
)
from .view_logic.chat_conversacion import (
    agregar_historial_conversacion,
    es_solicitud_reformulacion,
    formatear_historial_conversacion,
    formatear_historial_conversacion_solo_preguntas,
    obtener_ultima_respuesta_conversacion,
    obtener_ultimo_tipo_respuesta_conversacion,
    responder_pregunta_sobre_historial,
)
from .view_logic.chat_respuestas_ia import (
    generar_respuesta_controlada,
    limpiar_respuesta_ia,
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
        self.assertTrue(fragmentos[0]["contenido"].startswith("[Página 3]"))

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
    @override_settings(
        SGA_API_TOKEN_URL="http://127.0.0.1:8002/api/sga/token/",
        SGA_API_TOKEN_FIJO="TU_TOKEN_DE_INGRESO",
        SGA_API_USUARIO="nombre_usuario",
        SGA_API_PASSWORD="tu_contrasenia",
    )
    @patch("Bety_AI.views.cache")
    @patch("Bety_AI.views.requests.post")
    def test_obtener_token_api_sga_envia_campos_esperados(self, post_mock, cache_mock):
        cache_mock.get.return_value = ""
        post_mock.return_value.json.return_value = {
            "result": "ok",
            "token": "token_sga",
        }

        token, error = _obtener_token_api_sga()

        self.assertEqual(error, "")
        self.assertEqual(token, "token_sga")
        post_mock.assert_called_once_with(
            "http://127.0.0.1:8002/api/sga/token/",
            json={
                "tokenapputeq": "TU_TOKEN_DE_INGRESO",
                "usuario": "nombre_usuario",
                "contrasenia": "tu_contrasenia",
            },
            timeout=6,
        )
        cache_mock.set.assert_called_once()

    @override_settings(
        SGA_API_TOKEN_URL="http://127.0.0.1:8002/api/sga/token/",
        SGA_API_USUARIO_SESION_URL="http://127.0.0.1:8002/api/sga/usuario-sesion/",
        SGA_API_TOKEN_FIJO="TU_TOKEN_DE_INGRESO",
        SGA_API_USUARIO="nombre_usuario",
        SGA_API_PASSWORD="tu_contrasenia",
    )
    @patch("Bety_AI.views.cache")
    @patch("Bety_AI.views.requests.post")
    def test_cliente_sga_consulta_con_sessionid_y_token_api(self, post_mock, cache_mock):
        cache_mock.get.return_value = ""
        respuesta_token = Mock()
        respuesta_token.json.return_value = {
            "result": "ok",
            "token": "token_sga",
        }
        respuesta_usuario = Mock()
        respuesta_usuario.json.return_value = {
            "result": "ok",
            "usuario": {
                "usuario": "estudiante",
                "perfil": "estudiante",
                "nombre": "Maria",
                "facultad": "Ciencias Informaticas",
                "tipo_estudiante": "Pregrado",
                "materias": ["Programacion"],
            },
        }
        post_mock.side_effect = [respuesta_token, respuesta_usuario]

        perfil, error, token_sga = _obtener_usuario_sga_por_sessionid("abc123")

        self.assertEqual(error, "")
        self.assertEqual(token_sga, "")
        self.assertEqual(perfil["nombre"], "Maria")
        self.assertEqual(perfil["materias"], "Programacion")
        self.assertEqual(post_mock.call_count, 2)
        post_mock.assert_any_call(
            "http://127.0.0.1:8002/api/sga/token/",
            json={
                "tokenapputeq": "TU_TOKEN_DE_INGRESO",
                "usuario": "nombre_usuario",
                "contrasenia": "tu_contrasenia",
            },
            timeout=6,
        )
        post_mock.assert_any_call(
            "http://127.0.0.1:8002/api/sga/usuario-sesion/",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer token_sga",
            },
            json={"sessionid": "abc123"},
            timeout=6,
        )

    @override_settings(
        SGA_API_TOKEN_URL="http://127.0.0.1:8002/api/sga/token/",
        SGA_API_USUARIO_SESION_URL="http://127.0.0.1:8002/api/sga/usuario-sesion/",
        SGA_API_TOKEN_FIJO="TU_TOKEN_DE_INGRESO",
        SGA_API_USUARIO="nombre_usuario",
        SGA_API_PASSWORD="tu_contrasenia",
    )
    @patch("Bety_AI.views.cache")
    @patch("Bety_AI.views.requests.post")
    def test_cliente_sga_error_controlado_si_api_falla(self, post_mock, cache_mock):
        cache_mock.get.return_value = ""
        respuesta_token = Mock()
        respuesta_token.json.return_value = {
            "result": "ok",
            "token": "token_sga",
        }
        post_mock.side_effect = [
            respuesta_token,
            requests.exceptions.ConnectionError("conexion fallida"),
        ]

        perfil, error, token_sga = _obtener_usuario_sga_por_sessionid("abc123")

        self.assertIsNone(perfil)
        self.assertEqual(token_sga, "")
        self.assertIn("No se pudo validar tu sesion", error)

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
                "periodo_academico": "2026-S1",
            }
        })

        prompt = construir_contexto_usuario_prompt(perfil)
        filtros = construir_filtros_desde_perfil(perfil)

        self.assertFalse(perfil_estudiante_requiere_tipo(perfil))
        self.assertIn("- Tipo de estudiante: Pregrado", prompt)
        self.assertNotIn("tipo_estudio", filtros)
        self.assertEqual(filtros["perfiles"], "estudiante")
        self.assertEqual(filtros["grupos"], "Ciencias Informaticas")
        self.assertEqual(filtros["tipos_periodo"], "2026-S1")
        self.assertNotIn("carrera", filtros)
        self.assertIn(
            "pregrado",
            construir_pregunta_busqueda_con_perfil("como puedo matricularme", perfil),
        )

    def test_modo_web_no_pide_carrera_como_dato_obligatorio(self):
        perfil = {
            "perfil": "estudiante",
            "tipo_estudiante": "Pregrado",
            "facultad": "Ciencias Informaticas",
        }

        self.assertIsNone(obtener_siguiente_campo_perfil_web(perfil))

    def test_filtros_directos_se_alinean_con_metadata_documental(self):
        filtros = extraer_filtros_consulta({
            "perfil": "Docente invitado",
            "facultad": "Ciencias Informaticas",
            "periodo_academico": "2026-S1",
            "carrera": "Ingenieria en Sistemas",
        })

        self.assertEqual(filtros["perfiles"], "Docente invitado")
        self.assertEqual(filtros["grupos"], "Ciencias Informaticas")
        self.assertEqual(filtros["tipos_periodo"], "2026-S1")
        self.assertNotIn("perfil", filtros)
        self.assertNotIn("facultad", filtros)
        self.assertNotIn("periodo_academico", filtros)
        self.assertNotIn("carrera", filtros)

    def test_filtro_explicito_gana_sobre_perfil_usuario(self):
        filtros = combinar_filtros_consulta_y_perfil(
            {"perfiles": "Docente"},
            {"perfil": "Estudiante", "facultad": "Ciencias Informaticas"},
        )

        self.assertEqual(filtros["perfiles"], "Docente")
        self.assertEqual(filtros["grupos"], "Ciencias Informaticas")

    def test_filtros_flexibles_coinciden_con_listas_json_de_metadata(self):
        metadata = {
            "perfiles": '["Estudiante", "Docente"]',
            "grupos": '["Ciencias Informaticas"]',
            "tipos_periodo": '["2026-S1"]',
        }

        self.assertTrue(metadata_cumple_filtros_flexibles(
            metadata,
            {
                "perfiles": "docente",
                "grupos": "ciencias informaticas",
                "tipos_periodo": "2026-S1",
            },
        ))

    def test_describe_filtros_relajados_para_avisar_al_usuario(self):
        aviso = _describir_filtros_relajados(
            {"perfiles": "estudiante", "grupos": "FCC"},
            {"perfiles": "estudiante"},
        )

        self.assertIn("grupo/facultad: FCC", aviso)
        self.assertIn("filtros mas generales", aviso)

    def test_no_avisa_filtros_relajados_si_se_conservan(self):
        aviso = _describir_filtros_relajados(
            {"perfiles": "estudiante", "grupos": "FCC"},
            {"perfiles": "estudiante", "grupos": "FCC"},
        )

        self.assertEqual(aviso, "")

    def test_prompt_incluye_aviso_de_filtros_relajados(self):
        prompt = _construir_prompt_documental(
            pregunta="matricula",
            pregunta_busqueda="matricula pregrado",
            contexto_usuario="- Perfil: estudiante",
            historial_conversacion="",
            contexto="Documento relacionado",
            interpretacion_consulta={"formato_respuesta": "normal", "depende_historial": False},
            perfil_desambiguo_documento=False,
            aviso_filtros_relajados="No se encontro para grupo/facultad: FCC.",
        )

        self.assertIn("AVISO_FILTROS_RELAJADOS", prompt)
        self.assertIn("grupo/facultad: FCC", prompt)

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

    def test_ayudante_de_catedra_con_empate_prioriza_nivel_del_perfil_sin_excluir(self):
        # Antes de 2026-08-07 esto excluia el fragmento del nivel contrario.
        # Ahora, con score_ranking empatado, el del nivel del perfil gana el
        # orden pero el otro sigue disponible.
        pregunta = construir_pregunta_busqueda_con_perfil(
            "cuanto gano como ayudante de catedra",
            {"perfil": "estudiante", "tipo_estudiante": "Pregrado"},
        )
        fragmentos = [
            {
                "contenido": "El ayudante de catedra de posgrado recibe USD 520.",
                "metadata": {"id_documento": "2", "titulo": "Ayudantes de posgrado"},
                "coincidencia_lexica": 1,
                "score_ranking": 0.9,
            },
            {
                "contenido": "El ayudante de catedra de pregrado recibe el estipendio establecido.",
                "metadata": {"id_documento": "5", "titulo": "Ayudantes de pregrado"},
                "coincidencia_lexica": 1,
                "score_ranking": 0.9,
            },
        ]

        resultado = filtrar_fragmentos_por_tipo_estudiante(
            pregunta,
            {"perfil": "estudiante", "tipo_estudiante": "Pregrado"},
            fragmentos,
        )

        self.assertEqual(len(resultado), 2)
        self.assertIn("pregrado", resultado[0]["contenido"])
        self.assertIn("posgrado", resultado[1]["contenido"])
        self.assertAlmostEqual(
            resultado[1]["score_ranking"],
            0.9 + busqueda_fragmentos_module.PENALIZACION_NIVEL_CONTRARIO,
        )

    def test_consulta_posgrado_explicita_con_perfil_pregrado_recupera_el_documento(self):
        # Reproduce el incidente real del 2026-08-07: pregunta explicita por
        # posgrado con perfil pregrado. Antes del fix, filtrar_fragmentos_por_
        # tipo_estudiante descartaba el fragmento por completo.
        pregunta = "Cuales son los requisitos para ser ayudante de catedra de posgrado?"
        fragmentos = [
            {
                "contenido": (
                    "Ayudante de catedra de Posgrado. Requisitos: promedio minimo "
                    "9.0/10, carta de recomendacion, 15 horas semanales. Dirigido a "
                    "estudiantes de posgrado."
                ),
                "metadata": {"id_documento": "2", "titulo": "Documento 2"},
                "coincidencia_lexica": 1.0,
                "score_ranking": 0.9,
            },
        ]

        resultado = filtrar_fragmentos_por_tipo_estudiante(
            pregunta,
            {"perfil": "estudiante", "tipo_estudiante": "Pregrado"},
            fragmentos,
        )

        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]["metadata"]["id_documento"], "2")
        self.assertGreater(resultado[0]["score_ranking"], 0.9)

    @patch("Bety_AI.view_logic.busqueda_fragmentos.buscar_fragmentos")
    def test_fallback_no_devuelve_fragmentos_sin_pertinencia_lexica(self, buscar_mock):
        buscar_mock.side_effect = [
            [
                {
                    "contenido": "La guia de ayudantes de catedra establece requisitos academicos.",
                    "metadata": {
                        "titulo": "Guia de ayudantes de catedra",
                        "resumen_documento": "Seleccion de ayudantes de catedra.",
                    },
                    "coincidencia_lexica": 1,
                }
            ],
            [
                {
                    "contenido": "El estudiante debe registrar la solicitud de justificacion de inasistencias.",
                    "metadata": {
                        "titulo": "Manual para justificar inasistencia",
                        "resumen_documento": "Solicitud de justificacion de inasistencias.",
                    },
                    "coincidencia_lexica": 1,
                }
            ],
        ]

        fragmentos, filtros_aplicados = buscar_fragmentos_con_fallback(
            "como puedo justificar mi inasistencia",
            {"perfiles": "Estudiante"},
            total_resultados=3,
        )

        self.assertEqual(len(fragmentos), 1)
        self.assertIn("inasistencias", fragmentos[0]["contenido"])
        self.assertEqual(filtros_aplicados, {})

    @patch("Bety_AI.view_logic.busqueda_fragmentos.buscar_fragmentos")
    def test_fallback_no_devuelve_fragmentos_sin_coincidencia_con_consulta(self, buscar_mock):
        buscar_mock.return_value = [
            {
                "contenido": "La guia de ayudantes de catedra establece requisitos academicos.",
                "metadata": {
                    "titulo": "Guia de ayudantes de catedra",
                    "resumen_documento": "Seleccion de ayudantes de catedra.",
                },
                "coincidencia_lexica": 1,
            }
        ]

        fragmentos, filtros_aplicados = buscar_fragmentos_con_fallback(
            "como puedo justificar mi inasistencia",
            {"perfiles": "Estudiante"},
            total_resultados=3,
        )

        self.assertEqual(fragmentos, [])
        self.assertEqual(filtros_aplicados, {})

    def test_ayudantias_de_catedra_no_se_descarta_por_tema_mecanico(self):
        fragmento = {
            "contenido": "La guia institucional regula la seleccion de ayudantes de catedra de pregrado.",
            "metadata": {
                "titulo": "Guia ayudantes catedra pregrado profesional",
                "resumen_documento": "Lineamientos para ayudantes de catedra.",
            },
        }

        self.assertTrue(
            fragmento_pertinente_consulta("sobre las ayudantias de catedra", fragmento)
        )


class ClasificacionConsultaTests(SimpleTestCase):
    def test_pide_perfil_web_si_la_ia_clasifica_como_documental(self):
        pregunta = "Como puedo justificar mi inasistencia"
        interpretacion = {"tipo_operacion": "consulta_documental"}

        self.assertFalse(es_pregunta_fuera_ambito(pregunta))
        self.assertTrue(pregunta_necesita_perfil_web(pregunta, interpretacion))

    def test_no_pide_perfil_web_si_la_ia_clasifica_fuera_de_ambito(self):
        pregunta = "ayudas economicas"
        interpretacion = {"tipo_operacion": "fuera_ambito"}

        self.assertFalse(pregunta_necesita_perfil_web(pregunta, interpretacion))


class RespuestasControladasTests(SimpleTestCase):
    @patch("Bety_AI.view_logic.chat_respuestas_ia.consultar_qwen")
    def test_prompt_saludo_no_incluye_instrucciones_fuera_ambito(self, qwen_mock):
        qwen_mock.return_value = {
            "respuesta": "Hola, soy BettIA. En que puedo ayudarte con el SGA UTEQ?",
            "modelo": "qwen-test",
        }

        generar_respuesta_controlada("holaaaaaa", "SALUDO")

        prompt = qwen_mock.call_args.args[0]
        self.assertIn("Tipo de respuesta solicitada: SALUDO", prompt)
        self.assertIn("No digas que la consulta esta fuera de alcance.", prompt)
        self.assertNotIn("para que quieres saber eso", prompt.lower())

    @patch("Bety_AI.view_logic.chat_respuestas_ia.consultar_qwen")
    def test_prompt_fuera_ambito_tiene_instrucciones_propias(self, qwen_mock):
        qwen_mock.return_value = {
            "respuesta": "Eso no esta en mi base de informacion.",
            "modelo": "qwen-test",
        }

        generar_respuesta_controlada("cuentame un chiste", "FUERA_AMBITO")

        prompt = qwen_mock.call_args.args[0]
        self.assertIn("Tipo de respuesta solicitada: FUERA_AMBITO", prompt)
        self.assertIn("eso no esta en tu base de informacion", prompt)


class LimpiarRespuestaIaMetadataInternaTests(SimpleTestCase):
    def test_limpia_etiquetas_internas_del_bloque_fuente(self):
        respuesta = (
            "Los documentos disponibles son:\n\n"
            "1. Documento: Modelo Evaluativo SGA\n"
            "   - ID documento: 5\n"
            "   - Vigencia: VIGENTE\n"
            "   - Periodo: [\"Todos\"]\n"
            "   - Nivel académico detectado: General (no especifica nivel)\n"
        )

        limpia = limpiar_respuesta_ia(respuesta)

        self.assertNotIn("ID documento", limpia)
        self.assertNotIn("Vigencia:", limpia)
        self.assertNotIn("Periodo:", limpia)
        self.assertNotIn("Nivel académico detectado", limpia)
        self.assertIn("Los documentos disponibles son:", limpia)
        self.assertIn("Documento: Modelo Evaluativo SGA", limpia)
        self.assertNotIn("\n\n\n", limpia)

    def test_limpia_marcador_fuente_y_fragmento_vacio(self):
        respuesta = (
            "[FUENTE 1]\n"
            "Fragmento:\n"
            "Este es el contenido real que si debe verse.\n"
        )

        limpia = limpiar_respuesta_ia(respuesta)

        self.assertNotIn("[FUENTE", limpia)
        self.assertNotIn("Fragmento:", limpia)
        self.assertIn("Este es el contenido real que si debe verse.", limpia)

    def test_no_deja_vinetas_huerfanas(self):
        respuesta = "Respuesta breve.\n-\n1.\n"

        limpia = limpiar_respuesta_ia(respuesta)

        self.assertNotIn("-\n", limpia)
        self.assertEqual(limpia, "Respuesta breve.")

    def test_no_altera_respuesta_normal(self):
        respuesta = (
            "Para justificar una inasistencia debes:\n"
            "1. Ingresar al SGA con tu usuario institucional.\n"
            "2. Completar el formulario de justificacion.\n"
            "3. Adjuntar el respaldo correspondiente."
        )

        self.assertEqual(limpiar_respuesta_ia(respuesta), respuesta)

    def test_no_borra_prosa_que_menciona_las_palabras(self):
        respuesta = (
            "La vigencia de este documento es de dos años. "
            "El tipo de tramite depende del periodo academico en curso."
        )

        self.assertEqual(limpiar_respuesta_ia(respuesta), respuesta)


class InventarioDocumentosClasificacionTests(SimpleTestCase):
    def test_detecta_variantes_confirmadas_en_produccion(self):
        self.assertTrue(es_pregunta_inventario_documentos("Holaa, que documentos tienes?"))
        self.assertTrue(es_pregunta_inventario_documentos("Dime todos los documentos que tienes"))

    def test_detecta_sinonimos_razonables(self):
        self.assertTrue(es_pregunta_inventario_documentos("que documentos manejas"))
        self.assertTrue(es_pregunta_inventario_documentos("cuales son los documentos que tienes cargados"))
        self.assertTrue(es_pregunta_inventario_documentos("dame la lista de documentos"))

    def test_no_confunde_pregunta_documental_normal(self):
        self.assertFalse(es_pregunta_inventario_documentos("como justifico mi inasistencia"))
        self.assertFalse(
            es_pregunta_inventario_documentos("que dice el manual de convivencia sobre asistencia")
        )
        self.assertFalse(es_pregunta_inventario_documentos("que documento necesito para matricularme"))


class RespuestaInventarioDocumentosTests(SimpleTestCase):
    @patch("Bety_AI.views.listar_fragmentos_chroma")
    def test_lista_titulos_reales_deduplicados_y_ordenados(self, listar_mock):
        listar_mock.return_value = [
            {
                "id": "doc_5_frag_1",
                "contenido": "...",
                "metadata": {"id_documento": "5", "titulo": "Modelo Evaluativo SGA"},
            },
            {
                "id": "doc_5_frag_2",
                "contenido": "...",
                "metadata": {"id_documento": "5", "titulo": "Modelo Evaluativo SGA"},
            },
            {
                "id": "doc_7_frag_1",
                "contenido": "...",
                "metadata": {"id_documento": "7", "titulo": "Solicitud de Carnet Estudiantil"},
            },
            {
                "id": "doc_9_frag_1",
                "contenido": "...",
                "metadata": {
                    "id_documento": "9",
                    "titulo": "Manual para justificacion de inasistencia",
                },
            },
        ]

        respuesta = _construir_respuesta_inventario_documentos()

        self.assertEqual(
            respuesta,
            "Estos son los documentos que tengo disponibles:\n"
            "- Manual para justificacion de inasistencia\n"
            "- Modelo Evaluativo SGA\n"
            "- Solicitud de Carnet Estudiantil",
        )

    @patch("Bety_AI.views.listar_fragmentos_chroma", return_value=[])
    def test_responde_sin_documentos_cargados(self, listar_mock):
        self.assertEqual(
            _construir_respuesta_inventario_documentos(),
            "Por ahora no tengo documentos cargados en el sistema.",
        )

    @patch("Bety_AI.views.listar_fragmentos_chroma", side_effect=Exception("chroma caido"))
    def test_devuelve_none_si_chroma_falla(self, listar_mock):
        self.assertIsNone(_construir_respuesta_inventario_documentos())


@override_settings(CACHES={
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-conversacion",
    }
})
class HistorialConversacionTests(SimpleTestCase):
    def test_responde_primer_mensaje_desde_historial(self):
        conversation_id = "convtest01"
        agregar_historial_conversacion(conversation_id, "Hola", "Hola, soy BettIA.")
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

    def test_historial_solo_preguntas_no_incluye_respuestas_anteriores(self):
        conversation_id = "convtest-solo-preguntas-01"
        agregar_historial_conversacion(
            conversation_id,
            "documentos para ayuda economica por bajos recursos",
            "Lista completa de requisitos de bajos recursos.",
        )
        agregar_historial_conversacion(
            conversation_id,
            "y por excelencia academica",
            "Lista completa de requisitos de bajos recursos.",
        )

        historial_completo = formatear_historial_conversacion(conversation_id)
        historial_solo_preguntas = formatear_historial_conversacion_solo_preguntas(conversation_id)

        # El historial completo (para el router) sigue teniendo las respuestas.
        self.assertIn("BettIA:", historial_completo)
        self.assertIn("Lista completa de requisitos de bajos recursos.", historial_completo)

        # El historial reducido (para el prompt documental) no las tiene.
        self.assertNotIn("BettIA:", historial_solo_preguntas)
        self.assertNotIn("Lista completa de requisitos de bajos recursos.", historial_solo_preguntas)

        # Pero conserva las preguntas, en orden.
        indice_pregunta_1 = historial_solo_preguntas.find("documentos para ayuda economica por bajos recursos")
        indice_pregunta_2 = historial_solo_preguntas.find("y por excelencia academica")
        self.assertNotEqual(indice_pregunta_1, -1)
        self.assertNotEqual(indice_pregunta_2, -1)
        self.assertLess(indice_pregunta_1, indice_pregunta_2)

    def test_historial_solo_preguntas_usa_ultimos_turnos_sin_perder_primer_mensaje(self):
        conversation_id = "convtest-solo-preguntas-02"
        for indice in range(1, 7):
            agregar_historial_conversacion(
                conversation_id,
                f"Pregunta {indice}",
                f"Respuesta {indice}",
            )

        historial_solo_preguntas = formatear_historial_conversacion_solo_preguntas(conversation_id)

        self.assertNotIn("Pregunta 1\n", historial_solo_preguntas)
        self.assertNotIn("Pregunta 1", historial_solo_preguntas)
        self.assertIn("Pregunta 6", historial_solo_preguntas)
        self.assertNotIn("Respuesta 6", historial_solo_preguntas)

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
        request.session = type("SessionStub", (dict,), {})()

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
        self.assertEqual(
            obtener_ultimo_tipo_respuesta_conversacion(conversation_id),
            "REFORMULACION",
        )

    @patch("Bety_AI.views.consultar_qwen")
    @patch("Bety_AI.views.buscar_fragmentos_con_fallback")
    @patch("Bety_AI.views.guardar_interaccion_temporal", return_value=[])
    @patch("Bety_AI.views.generar_reformulacion_respuesta")
    @patch("Bety_AI.views.interpretar_consulta_ia")
    def test_api_redispara_busqueda_si_reformulacion_sigue_a_fuera_ambito(
        self,
        interpretar_mock,
        reformular_mock,
        guardar_temporal_mock,
        buscar_mock,
        qwen_mock,
    ):
        conversation_id = "convtest-reformula-tras-fuera-ambito"
        agregar_historial_conversacion(
            conversation_id,
            "Que me puedes decir sobre los ayudantes de catedra",
            "No hay informacion suficiente sobre eso.",
            "FUERA_AMBITO",
        )
        interpretar_mock.return_value = {
            "tipo_operacion": "reformulacion",
            "consulta_normalizada": "",
            "consulta_busqueda": "",
            "depende_historial": True,
            "formato_respuesta": "normal",
            "palabras_clave": [],
            "filtros_sugeridos": {},
            "modelo": "qwen-test",
        }
        buscar_mock.return_value = (
            [
                {
                    "contenido": "Los ayudantes de catedra deben cumplir estos requisitos.",
                    "metadata": {
                        "titulo": "Guia ayudantes de catedra",
                        "id_documento": "9",
                        "tipo_documento": "GUIA",
                    },
                    "coincidencia_lexica": 1,
                }
            ],
            {},
        )
        qwen_mock.return_value = {
            "respuesta": "Los ayudantes de catedra deben cumplir estos requisitos.",
            "modelo": "qwen-final",
        }

        request = APIRequestFactory().post(
            "/api/chat/",
            {
                "pregunta": "explicame mejor",
                "conversation_id": conversation_id,
            },
            format="json",
        )
        request.session = type("SessionStub", (dict,), {})()

        response = api_consulta_ia(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["tipo_respuesta"], "RESPUESTA")
        buscar_mock.assert_called_once()
        reformular_mock.assert_not_called()
        self.assertEqual(
            obtener_ultimo_tipo_respuesta_conversacion(conversation_id),
            "RESPUESTA",
        )

    @patch("Bety_AI.views.interpretar_consulta_ia")
    @patch("Bety_AI.views.buscar_fragmentos_con_fallback")
    @patch("Bety_AI.views.listar_fragmentos_chroma")
    @patch("Bety_AI.views.guardar_interaccion_temporal", return_value=[])
    def test_api_responde_inventario_sin_pasar_por_el_router(
        self,
        guardar_temporal_mock,
        listar_mock,
        buscar_mock,
        interpretar_mock,
    ):
        listar_mock.return_value = [
            {
                "id": "doc_5_frag_1",
                "contenido": "...",
                "metadata": {"id_documento": "5", "titulo": "Modelo Evaluativo SGA"},
            },
            {
                "id": "doc_7_frag_1",
                "contenido": "...",
                "metadata": {"id_documento": "7", "titulo": "Solicitud de Carnet Estudiantil"},
            },
            {
                "id": "doc_9_frag_1",
                "contenido": "...",
                "metadata": {
                    "id_documento": "9",
                    "titulo": "Manual para justificacion de inasistencia",
                },
            },
        ]

        request = APIRequestFactory().post(
            "/api/chat/",
            {
                "pregunta": "Holaa, que documentos tienes?",
                "conversation_id": "convtest-inventario",
            },
            format="json",
        )
        request.session = type("SessionStub", (dict,), {})()

        response = api_consulta_ia(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["tipo_respuesta"], "INVENTARIO_DOCUMENTOS")
        self.assertIn("Modelo Evaluativo SGA", response.data["respuesta"])
        self.assertIn("Solicitud de Carnet Estudiantil", response.data["respuesta"])
        self.assertIn("Manual para justificacion de inasistencia", response.data["respuesta"])
        interpretar_mock.assert_not_called()
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

    def test_normaliza_interpretacion_no_duplica_pregunta_sin_consulta_normalizada(self):
        # Bug real: cuando el router no devuelve consulta_normalizada, caia al
        # fallback de pregunta_limpia y se volvia a concatenar aparte -- la
        # pregunta completa quedaba duplicada dentro de consulta_busqueda.
        pregunta = "cual es el horario de la biblioteca"
        interpretacion = normalizar_interpretacion(
            {"tipo_operacion": "consulta_documental"},
            pregunta,
        )

        self.assertEqual(interpretacion["consulta_busqueda"].count(pregunta), 1)
        self.assertEqual(interpretacion["consulta_busqueda"], pregunta)
        # El campo consulta_normalizada en si mantiene el fallback (lo usan
        # otros consumidores, ej. _construir_pregunta_busqueda como ultimo
        # recurso si consulta_busqueda faltara).
        self.assertEqual(interpretacion["consulta_normalizada"], pregunta)

    def test_interpretacion_fallback_no_duplica_pregunta(self):
        # interpretacion_fallback (usado cuando el router LLM falla) siempre
        # setea consulta_normalizada=pregunta explicitamente -- es el caso que
        # disparaba la duplicacion el 100% de las veces.
        pregunta = "cual es el horario de la biblioteca"
        interpretacion = interpretacion_fallback(pregunta)

        self.assertEqual(interpretacion["consulta_busqueda"].count(pregunta), 1)
        self.assertEqual(interpretacion["consulta_busqueda"], pregunta)

    def test_normaliza_interpretacion_mantiene_consulta_normalizada_distinta(self):
        # Caso real del incidente: el router SI devolvio una consulta_normalizada
        # genuinamente distinta de la pregunta (no un eco). Debe seguir
        # apareciendo una sola vez, sin regresion.
        pregunta = "explicame mejor"
        interpretacion = normalizar_interpretacion(
            {
                "tipo_operacion": "consulta_documental",
                "consulta_normalizada": "requisitos para ser ayudante de catedra",
                "palabras_clave": ["ayudante de catedra", "requisitos", "pregrado", "grado"],
            },
            pregunta,
        )

        self.assertEqual(interpretacion["consulta_busqueda"].count(pregunta), 1)
        self.assertEqual(interpretacion["consulta_busqueda"].count("requisitos para ser ayudante de catedra"), 1)
        self.assertEqual(
            interpretacion["consulta_busqueda"],
            "explicame mejor requisitos para ser ayudante de catedra "
            "ayudante de catedra requisitos pregrado grado",
        )

    def test_extrae_json_interpretacion_desde_markdown(self):
        data = extraer_json_interpretacion(
            '```json\n{"tipo_operacion": "consulta_documental", "formato_respuesta": "lista"}\n```'
        )

        self.assertEqual(data["tipo_operacion"], "consulta_documental")
        self.assertEqual(data["formato_respuesta"], "lista")

    def test_normaliza_interpretacion_de_saludo_e_identidad(self):
        saludo = normalizar_interpretacion({"tipo_operacion": "saludo"}, "holaaaa")
        identidad = normalizar_interpretacion({"tipo_operacion": "identidad"}, "quien eres")

        self.assertEqual(saludo["tipo_operacion"], "saludo")
        self.assertEqual(identidad["tipo_operacion"], "identidad")

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

    def test_pregunta_con_tema_claro_no_se_normaliza_como_reformulacion(self):
        interpretacion = normalizar_interpretacion(
            {
                "tipo_operacion": "reformulacion",
                "consulta_normalizada": "reformatear respuesta anterior",
                "depende_historial": True,
                "formato_respuesta": "normal",
            },
            "como evalua el sga",
        )

        self.assertEqual(interpretacion["tipo_operacion"], "consulta_documental")
        self.assertFalse(interpretacion["depende_historial"])

    def test_views_no_reformula_si_la_pregunta_tiene_tema_nuevo(self):
        conversation_id = "convtest-debe-reformular-tema-nuevo"
        self.assertFalse(
            _debe_reformular(
                "como evalua el sga",
                {"tipo_operacion": "reformulacion", "depende_historial": True},
                conversation_id,
            )
        )
        self.assertTrue(
            _debe_reformular(
                "dame una tabla",
                {"tipo_operacion": "reformulacion", "depende_historial": True},
                conversation_id,
            )
        )

    def test_construir_pregunta_busqueda_no_duplica_pregunta_con_depende_historial(self):
        # Caso real de produccion: "explicame mejor" tras un FUERA_AMBITO sobre
        # horario de biblioteca, con el router anclando consulta_normalizada al
        # tema de un turno anterior (ayudante de catedra). pregunta_interpretada
        # (via consulta_busqueda) ya arranca con la pregunta limpia, asi que
        # _construir_pregunta_busqueda no debe volver a concatenarla aparte.
        pregunta = "explicame mejor"
        ultima_pregunta = "Cual es el horario de la biblioteca?"
        interpretacion_consulta = {
            "tipo_operacion": "consulta_documental",
            "consulta_normalizada": "requisitos para ser ayudante de catedra",
            "consulta_busqueda": (
                "explicame mejor requisitos para ser ayudante de catedra "
                "ayudante de catedra requisitos pregrado grado"
            ),
            "depende_historial": True,
        }

        pregunta_busqueda = _construir_pregunta_busqueda(
            pregunta, ultima_pregunta, interpretacion_consulta, {}
        )

        self.assertEqual(pregunta_busqueda.count(pregunta), 1)
        self.assertEqual(
            pregunta_busqueda,
            "Cual es el horario de la biblioteca? explicame mejor requisitos "
            "para ser ayudante de catedra ayudante de catedra requisitos "
            "pregrado grado",
        )

    def test_construir_pregunta_busqueda_no_pierde_pregunta_si_interpretada_no_la_incluye(self):
        # Caso adversarial: consulta_busqueda NO contiene la pregunta original
        # (ej. si el router devolviera solo un tema sin ecoar el mensaje). Al
        # sacar el "pregunta" suelto del join para no duplicar, no debe
        # perderse -- _construir_pregunta_busqueda tiene que agregarlo de
        # vuelta porque pregunta_interpretada no lo trae.
        pregunta = "explicame mejor"
        ultima_pregunta = "Cual es el horario de la biblioteca?"
        interpretacion_consulta = {
            "tipo_operacion": "consulta_documental",
            "consulta_normalizada": "requisitos para ser ayudante de catedra",
            "consulta_busqueda": "requisitos para ser ayudante de catedra",
            "depende_historial": True,
        }

        pregunta_busqueda = _construir_pregunta_busqueda(
            pregunta, ultima_pregunta, interpretacion_consulta, {}
        )

        self.assertEqual(pregunta_busqueda.count(pregunta), 1)
        self.assertIn(pregunta, pregunta_busqueda)
        self.assertEqual(
            pregunta_busqueda,
            "Cual es el horario de la biblioteca? explicame mejor requisitos "
            "para ser ayudante de catedra",
        )

    def test_construir_pregunta_busqueda_no_da_falso_positivo_con_pregunta_corta(self):
        # "mas" es substring de "ademas" (y de otras palabras), pero eso no
        # significa que pregunta_interpretada ya incluya la pregunta -- un
        # chequeo con "in" daria falso positivo y perderia "mas" del todo.
        # Con startswith (prefijo, la garantia real de normalizar_interpretacion)
        # esto no pasa: "mas" se agrega igual porque pregunta_interpretada no
        # arranca con ella.
        pregunta = "mas"
        ultima_pregunta = "Cual es el horario de la biblioteca?"
        interpretacion_consulta = {
            "tipo_operacion": "consulta_documental",
            "consulta_normalizada": "informacion ademas de requisitos",
            "consulta_busqueda": "informacion ademas de requisitos para ser ayudante de catedra",
            "depende_historial": True,
        }

        pregunta_busqueda = _construir_pregunta_busqueda(
            pregunta, ultima_pregunta, interpretacion_consulta, {}
        )

        self.assertEqual(
            pregunta_busqueda,
            "Cual es el horario de la biblioteca? mas informacion ademas de "
            "requisitos para ser ayudante de catedra",
        )

    def test_construir_pregunta_busqueda_depende_historial_sin_ultima_pregunta(self):
        # depende_historial=True pero sin turno anterior (conversacion nueva o
        # historial vacio): no debe romper ni duplicar, cae al mismo camino
        # que cuando no depende del historial.
        pregunta = "explicame mejor"
        interpretacion_consulta = {
            "tipo_operacion": "consulta_documental",
            "consulta_normalizada": "requisitos para ser ayudante de catedra",
            "consulta_busqueda": "explicame mejor requisitos para ser ayudante de catedra",
            "depende_historial": True,
        }

        pregunta_busqueda = _construir_pregunta_busqueda(
            pregunta, "", interpretacion_consulta, {}
        )

        self.assertEqual(pregunta_busqueda.count(pregunta), 1)
        self.assertEqual(
            pregunta_busqueda,
            "explicame mejor requisitos para ser ayudante de catedra",
        )

    def test_obtiene_ultimo_tipo_respuesta_de_conversacion(self):
        conversation_id = "convtest-tipo-respuesta"
        agregar_historial_conversacion(conversation_id, "Pregunta 1", "Respuesta 1", "RESPUESTA")
        agregar_historial_conversacion(conversation_id, "Pregunta 2", "Respuesta 2", "FUERA_AMBITO")

        self.assertEqual(
            obtener_ultimo_tipo_respuesta_conversacion(conversation_id),
            "FUERA_AMBITO",
        )

    def test_debe_reformular_no_intercepta_si_ultima_respuesta_fue_fuera_ambito(self):
        conversation_id = "convtest-debe-reformular-fuera-ambito"
        agregar_historial_conversacion(
            conversation_id,
            "Que me puedes decir sobre los ayudantes de catedra",
            "No hay informacion suficiente sobre eso.",
            "FUERA_AMBITO",
        )

        self.assertFalse(
            _debe_reformular(
                "explicame mejor",
                {"tipo_operacion": "reformulacion", "depende_historial": True},
                conversation_id,
            )
        )

    @patch("Bety_AI.views.consultar_qwen")
    @patch("Bety_AI.views.guardar_interaccion_temporal", return_value=[])
    @patch("Bety_AI.views.interpretar_consulta_ia")
    def test_api_pide_perfil_web_para_ayudas_economicas_sin_contexto(
        self,
        interpretar_mock,
        guardar_temporal_mock,
        qwen_mock,
    ):
        interpretar_mock.return_value = {
            "tipo_operacion": "consulta_documental",
            "consulta_normalizada": "ayudas economicas",
            "consulta_busqueda": "ayudas economicas",
            "depende_historial": False,
            "formato_respuesta": "normal",
            "palabras_clave": [],
            "filtros_sugeridos": {},
            "modelo": "qwen-test",
        }
        request = APIRequestFactory().post(
            "/api/chat/",
            {
                "pregunta": "ayudas economicas",
                "conversation_id": "convtest-ayudas-web",
            },
            format="json",
        )
        request.session = type("SessionStub", (dict,), {})()

        response = api_consulta_ia(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["tipo_respuesta"], "SOLICITUD_CONTEXTO_WEB")
        self.assertIn("eres estudiante", response.data["respuesta"])
        interpretar_mock.assert_called_once()
        qwen_mock.assert_not_called()
        guardar_temporal_mock.assert_called_once()

    @patch("Bety_AI.views.buscar_fragmentos_con_fallback")
    @patch("Bety_AI.views.guardar_interaccion_temporal", return_value=[])
    @patch("Bety_AI.views.generar_respuesta_controlada")
    @patch("Bety_AI.views.interpretar_consulta_ia")
    def test_api_saludo_lo_decide_interpretacion_ia(
        self,
        interpretar_mock,
        respuesta_controlada_mock,
        guardar_temporal_mock,
        buscar_mock,
    ):
        interpretar_mock.return_value = {
            "tipo_operacion": "saludo",
            "consulta_normalizada": "holaaaa",
            "consulta_busqueda": "holaaaa",
            "depende_historial": False,
            "formato_respuesta": "normal",
            "palabras_clave": [],
            "filtros_sugeridos": {},
            "modelo": "qwen-test",
        }
        respuesta_controlada_mock.return_value = {
            "respuesta": "Hola, soy BettIA. En que puedo ayudarte con el SGA UTEQ?",
            "modelo": "qwen-control",
        }
        request = APIRequestFactory().post(
            "/api/chat/",
            {
                "pregunta": "holaaaa",
                "conversation_id": "convtest-saludo-ia",
            },
            format="json",
        )
        request.session = type("SessionStub", (dict,), {})()

        response = api_consulta_ia(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["tipo_respuesta"], "SALUDO")
        interpretar_mock.assert_called_once()
        respuesta_controlada_mock.assert_called_once()
        buscar_mock.assert_not_called()
        guardar_temporal_mock.assert_called_once()
        self.assertEqual(
            obtener_ultimo_tipo_respuesta_conversacion("convtest-saludo-ia"),
            "SALUDO",
        )

    @patch("Bety_AI.views.buscar_fragmentos_con_fallback")
    @patch("Bety_AI.views.guardar_interaccion_temporal", return_value=[])
    @patch("Bety_AI.views.interpretar_consulta_ia")
    def test_api_historial_lo_decide_interpretacion_ia(
        self,
        interpretar_mock,
        guardar_temporal_mock,
        buscar_mock,
    ):
        conversation_id = "convtest-historial-ia"
        agregar_historial_conversacion(conversation_id, "Pregunta inicial", "Respuesta inicial")
        interpretar_mock.return_value = {
            "tipo_operacion": "historial",
            "consulta_normalizada": "primera pregunta",
            "consulta_busqueda": "primera pregunta",
            "depende_historial": False,
            "formato_respuesta": "normal",
            "palabras_clave": [],
            "filtros_sugeridos": {},
            "modelo": "qwen-test",
        }
        request = APIRequestFactory().post(
            "/api/chat/",
            {
                "pregunta": "cual fue mi primera pregunta?",
                "conversation_id": conversation_id,
            },
            format="json",
        )
        request.session = type("SessionStub", (dict,), {})()

        response = api_consulta_ia(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["tipo_respuesta"], "HISTORIAL_CONVERSACION")
        self.assertIn("Pregunta inicial", response.data["respuesta"])
        interpretar_mock.assert_called_once()
        buscar_mock.assert_not_called()
        guardar_temporal_mock.assert_called_once()
        self.assertEqual(
            obtener_ultimo_tipo_respuesta_conversacion(conversation_id),
            "HISTORIAL_CONVERSACION",
        )

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
                "usuario": {
                    "perfil": "estudiante",
                    "tipo_estudiante": "pregrado",
                    "facultad": "Computacion",
                },
            },
            format="json",
        )
        request.session = type("SessionStub", (dict,), {})()

        response = api_consulta_ia(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["tipo_respuesta"], "RESPUESTA")
        self.assertIn("ayudas economicas", buscar_mock.call_args.kwargs["pregunta"])
        guardar_temporal_mock.assert_called_once()
        self.assertEqual(
            obtener_ultimo_tipo_respuesta_conversacion("convtest05"),
            "RESPUESTA",
        )

    @patch("Bety_AI.views.consultar_qwen")
    @patch("Bety_AI.views.buscar_fragmentos_con_fallback")
    @patch("Bety_AI.views.guardar_interaccion_temporal", return_value=[])
    @patch("Bety_AI.views.interpretar_consulta_ia")
    def test_prompt_documental_no_lleva_respuestas_anteriores_pero_router_si(
        self,
        interpretar_mock,
        guardar_temporal_mock,
        buscar_mock,
        qwen_mock,
    ):
        conversation_id = "convtest-historial-solo-preguntas"
        agregar_historial_conversacion(
            conversation_id,
            "documentos para ayuda economica por bajos recursos",
            "Lista completa de requisitos de bajos recursos.",
        )

        interpretar_mock.return_value = {
            "tipo_operacion": "consulta_documental",
            "consulta_normalizada": "ayuda economica por excelencia academica",
            "consulta_busqueda": "y por excelencia academica ayuda economica por excelencia academica",
            "depende_historial": False,
            "formato_respuesta": "normal",
            "palabras_clave": [],
            "filtros_sugeridos": {},
            "modelo": "qwen-test",
        }
        buscar_mock.return_value = (
            [_fragmento("2", "Ayudas economicas", contenido="Requisitos de excelencia academica.")],
            {},
        )
        qwen_mock.return_value = {
            "respuesta": "Requisitos de excelencia academica.",
            "modelo": "qwen-final",
        }

        request = APIRequestFactory().post(
            "/api/chat/",
            {
                "pregunta": "y por excelencia academica",
                "conversation_id": conversation_id,
                "usuario": {
                    "perfil": "estudiante",
                    "tipo_estudiante": "pregrado",
                    "facultad": "Computacion",
                },
            },
            format="json",
        )
        request.session = type("SessionStub", (dict,), {})()

        response = api_consulta_ia(request)

        self.assertEqual(response.status_code, 200)

        # El router sigue recibiendo el historial completo, con las respuestas.
        historial_recibido_por_router = interpretar_mock.call_args.args[1]
        self.assertIn("BettIA:", historial_recibido_por_router)
        self.assertIn("Lista completa de requisitos de bajos recursos.", historial_recibido_por_router)

        # El prompt documental (lo que arma la respuesta final) no lleva la
        # respuesta anterior completa -- solo el hilo de preguntas.
        prompt_documental = qwen_mock.call_args.args[0]
        self.assertNotIn("BettIA:", prompt_documental)
        self.assertNotIn("Lista completa de requisitos de bajos recursos.", prompt_documental)
        self.assertIn("documentos para ayuda economica por bajos recursos", prompt_documental)

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
                    "perfiles": ["ESTUDIANTE"],
                    "grupos": ["POSGRADO"],
                    "tipos_periodo": ["2026-S1"],
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
        self.assertEqual(metadata_base["perfiles"], '["ESTUDIANTE"]')
        self.assertEqual(metadata_base["grupos"], '["POSGRADO"]')
        self.assertEqual(metadata_base["tipos_periodo"], '["2026-S1"]')
        self.assertNotIn("perfil", metadata_base)
        self.assertNotIn("periodo", metadata_base)
        self.assertNotIn("grupo", metadata_base)
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
        self.assertNotIn("perfil", metadata_base)
        self.assertNotIn("rol", metadata_base)

    @patch("Bety_AI.views.guardar_fragmentos_documento", return_value=1)
    @patch("Bety_AI.views.eliminar_documento_chroma")
    @patch("Bety_AI.views.eliminar_version_chroma")
    @patch(
        "Bety_AI.views.dividir_documento_en_fragmentos",
        return_value=([{"contenido": "fragmento nuevo"}], "characters"),
    )
    def test_guarda_solo_metadata_documental_permitida(
        self,
        dividir_mock,
        eliminar_version_mock,
        eliminar_documento_mock,
        guardar_mock,
    ):
        request = self.factory.post(
            "/api/integracion/documentos/guardar-chroma/",
            {
                "id_documento": "DOC-META",
                "id_version": "8",
                "uuid_documento": "uuid-doc",
                "uuid_version": "uuid-ver",
                "anio_documento": "2026",
                "ambito": "ACADEMICO",
                "tipo_documento": "MANUAL",
                "nombre_archivo": "manual.pdf",
                "documento_url": "https://documentos.uteq.edu.ec/manual.pdf",
                "texto_extraido": "Texto suficientemente largo para superar el minimo de caracteres. " * 3,
                "metadata": {
                    "perfiles": ["Estudiante", "Docente"],
                    "grupos": ["Computacion"],
                    "tipos_periodo": ["Nivelacion", "Grado"],
                    "resumen_documento": "Resumen generado por IA.",
                    "temas_detectados": ["matricula"],
                    "perfiles_acceso": [{"id": 1, "nombre": "Estudiante"}],
                    "id_perfil_externo": [1],
                    "grupos_acceso": [{"id": 10, "nombre": "Computacion"}],
                    "id_grupo_externo": [10],
                    "tipos_periodo_acceso": [{"id": 1, "nombre": "Nivelacion"}],
                    "id_tipo_periodo_externo": [1],
                    "fuente": "Django_Modulo_GestionDocumentosLegales",
                    "porcentaje_texto": "100.0",
                    "porcentaje_imagenes": "0.0",
                    "advertencias": ["texto repetido"],
                    "requiere_revision_humana": True,
                    "perfil": "",
                    "grupo": "",
                    "periodo": "",
                    "carrera": "GENERAL",
                    "tipo_estudio": "GENERAL",
                },
            },
            format="json",
        )

        response = api_procesar_documento(request)

        self.assertEqual(response.status_code, 200)
        metadata_base = guardar_mock.call_args.kwargs["metadata_base"]
        self.assertEqual(metadata_base["id_version"], "8")
        self.assertEqual(metadata_base["uuid_documento"], "uuid-doc")
        self.assertEqual(metadata_base["uuid_version"], "uuid-ver")
        self.assertEqual(metadata_base["anio_documento"], "2026")
        self.assertEqual(metadata_base["tipo_documento"], "MANUAL")
        self.assertEqual(metadata_base["nombre_archivo"], "manual.pdf")
        self.assertEqual(metadata_base["documento_url"], "https://documentos.uteq.edu.ec/manual.pdf")
        self.assertEqual(metadata_base["perfiles"], '["Estudiante", "Docente"]')
        self.assertEqual(metadata_base["grupos"], '["Computacion"]')
        self.assertEqual(metadata_base["tipos_periodo"], '["Nivelacion", "Grado"]')
        self.assertEqual(metadata_base["resumen_documento"], "Resumen generado por IA.")

        for clave in [
            "porcentaje_texto",
            "porcentaje_imagenes",
            "advertencias",
            "requiere_revision_humana",
            "perfil",
            "grupo",
            "periodo",
            "carrera",
            "tipo_estudio",
            "ambito",
            "perfiles_acceso",
            "id_perfil_externo",
            "grupos_acceso",
            "id_grupo_externo",
            "tipos_periodo_acceso",
            "id_tipo_periodo_externo",
            "fuente",
            "temas_detectados",
        ]:
            self.assertNotIn(clave, metadata_base)

    @patch("Bety_AI.views.guardar_fragmentos_documento", return_value=1)
    @patch("Bety_AI.views.eliminar_documento_chroma")
    @patch("Bety_AI.views.eliminar_version_chroma")
    @patch(
        "Bety_AI.views.dividir_documento_en_fragmentos",
        return_value=([{"contenido": "fragmento nuevo"}], "characters"),
    )
    def test_tipo_periodo_se_guarda_como_tipos_periodo(
        self,
        dividir_mock,
        eliminar_version_mock,
        eliminar_documento_mock,
        guardar_mock,
    ):
        request = self.factory.post(
            "/api/integracion/documentos/guardar-chroma/",
            {
                "id_documento": "DOC-PERIODO",
                "texto_extraido": "Texto suficientemente largo para superar el minimo de caracteres. " * 3,
                "metadata": {
                    "tipo_periodo": ["Nivelacion", "Grado"],
                },
            },
            format="json",
        )

        response = api_procesar_documento(request)

        self.assertEqual(response.status_code, 200)
        metadata_base = guardar_mock.call_args.kwargs["metadata_base"]
        self.assertEqual(metadata_base["tipos_periodo"], '["Nivelacion", "Grado"]')
        self.assertNotIn("tipo_periodo", metadata_base)

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


class ActualizarLinkDocumentoTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    @patch("Bety_AI.views.actualizar_metadata_version_chroma", return_value=3)
    def test_actualiza_link_por_uuid_version(self, actualizar_mock):
        request = self.factory.post(
            "/api/integracion/documentos/actualizar-link/",
            {
                "uuid_version": "uuid-version-123",
                "documento_url": "https://documentos.uteq.edu.ec/doc/123",
            },
            format="json",
        )

        response = api_actualizar_link_documento(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["estado_procesamiento"], "LINK_ACTUALIZADO")
        self.assertEqual(response.data["fragmentos_actualizados"], 3)
        actualizar_mock.assert_called_once_with(
            "uuid-version-123",
            {"documento_url": "https://documentos.uteq.edu.ec/doc/123"},
        )

    @patch("Bety_AI.views.actualizar_metadata_version_chroma")
    def test_rechaza_link_inseguro(self, actualizar_mock):
        request = self.factory.post(
            "/api/integracion/documentos/actualizar-link/",
            {
                "uuid_version": "uuid-version-123",
                "documento_url": "javascript:alert(1)",
            },
            format="json",
        )

        response = api_actualizar_link_documento(request)

        self.assertEqual(response.status_code, 400)
        actualizar_mock.assert_not_called()

    @patch("Bety_AI.views.actualizar_metadata_version_chroma", return_value=0)
    def test_devuelve_404_si_no_hay_fragmentos_para_la_version(self, actualizar_mock):
        request = self.factory.post(
            "/api/integracion/documentos/actualizar-link/",
            {
                "uuid_version": "uuid-version-ausente",
                "documento_url": "https://documentos.uteq.edu.ec/doc/404",
            },
            format="json",
        )

        response = api_actualizar_link_documento(request)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["estado_procesamiento"], "NO_ENCONTRADO")
        actualizar_mock.assert_called_once()


class FuentesRespuestaTests(SimpleTestCase):
    def test_fuente_incluye_url_segura_sin_cambiar_titulo_visible(self):
        fuentes = _construir_fuentes_respuesta([
            _fragmento(
                "DOC-1",
                "Reglamento academico",
                {
                    "nombre_archivo": "reglamento.pdf",
                    "pagina_inicio": 2,
                    "pagina_fin": 2,
                    "documento_url": "https://documentos.uteq.edu.ec/doc/1",
                },
            )
        ])

        self.assertEqual(fuentes[0]["titulo"], "Reglamento academico")
        self.assertEqual(fuentes[0]["url"], "https://documentos.uteq.edu.ec/doc/1")
        self.assertEqual(fuentes[0]["pagina"], "2")

    def test_fuente_capitaliza_primera_letra_del_titulo(self):
        fuentes = _construir_fuentes_respuesta([
            _fragmento("DOC-1", "POLITICA DE PROTECCION DE DATOS PERSONALES")
        ])

        self.assertEqual(
            fuentes[0]["titulo"],
            "Politica de proteccion de datos personales",
        )

    def test_fuente_no_incluye_url_insegura(self):
        fuentes = _construir_fuentes_respuesta([
            _fragmento(
                "DOC-1",
                "Reglamento academico",
                {"documento_url": "javascript:alert(1)"},
            )
        ])

        self.assertNotIn("url", fuentes[0])


class ActualizarMetadataVersionChromaServiceTests(SimpleTestCase):
    @patch("Bety_AI.services.chroma_service.obtener_coleccion")
    def test_actualiza_metadata_de_todos_los_fragmentos_de_la_version(self, obtener_mock):
        coleccion = Mock()
        coleccion.get.return_value = {
            "ids": ["frag-1", "frag-2"],
            "metadatas": [
                {"uuid_version": "uuid-version-123", "titulo": "Doc 1"},
                {"uuid_version": "uuid-version-123", "titulo": "Doc 1", "pagina_inicio": 2},
            ],
        }
        obtener_mock.return_value = coleccion

        total = chroma_service.actualizar_metadata_version_chroma(
            "uuid-version-123",
            {"documento_url": "https://documentos.uteq.edu.ec/doc/123"},
        )

        self.assertEqual(total, 2)
        coleccion.get.assert_called_once_with(
            where={"uuid_version": "uuid-version-123"},
            include=["metadatas"],
        )
        coleccion.update.assert_called_once_with(
            ids=["frag-1", "frag-2"],
            metadatas=[
                {
                    "uuid_version": "uuid-version-123",
                    "titulo": "Doc 1",
                    "documento_url": "https://documentos.uteq.edu.ec/doc/123",
                },
                {
                    "uuid_version": "uuid-version-123",
                    "titulo": "Doc 1",
                    "pagina_inicio": 2,
                    "documento_url": "https://documentos.uteq.edu.ec/doc/123",
                },
            ],
        )

    @patch("Bety_AI.services.chroma_service.obtener_coleccion")
    def test_devuelve_cero_si_no_encuentra_fragmentos(self, obtener_mock):
        coleccion = Mock()
        coleccion.get.return_value = {"ids": [], "metadatas": []}
        obtener_mock.return_value = coleccion

        total = chroma_service.actualizar_metadata_version_chroma(
            "uuid-version-ausente",
            {"documento_url": "https://documentos.uteq.edu.ec/doc/404"},
        )

        self.assertEqual(total, 0)
        coleccion.update.assert_not_called()


def _fragmento(doc_id, titulo, metadata_extra=None, contenido="contenido"):
    metadata = {"id_documento": doc_id, "titulo": titulo}
    if metadata_extra:
        metadata.update(metadata_extra)
    return {"contenido": contenido, "metadata": metadata, "coincidencia_lexica": 1.0, "distancia": 1.0}


class FiltrarFragmentosConfiablesTests(SimpleTestCase):
    def test_fragmento_limpio_sin_flags_pasa(self):
        fragmentos = [_fragmento("13", "Manual limpio")]

        resultado = filtrar_fragmentos_confiables(fragmentos)

        self.assertEqual(resultado, fragmentos)

    def test_fragmento_marcado_requiere_revision_humana_se_descarta(self):
        limpio = _fragmento("13", "Manual limpio")
        sucio = _fragmento("4", "Guia matriculacion pregrado", {"requiere_revision_humana": "true"})

        resultado = filtrar_fragmentos_confiables([limpio, sucio])

        self.assertEqual(resultado, [limpio])

    def test_fragmento_marcado_por_advertencias_json_se_descarta(self):
        limpio = _fragmento("13", "Manual limpio")
        sucio = _fragmento(
            "3",
            "Guia ayudantes catedra posgrado",
            {"advertencias": '["repeticion excesiva de frases"]'},
        )

        resultado = filtrar_fragmentos_confiables([limpio, sucio])

        self.assertEqual(resultado, [limpio])

    def test_requiere_revision_humana_true_capitalizado_se_descarta(self):
        # Cubre la variante "True" (str(bool) de Python) ademas de "true" (JSON).
        sucio = _fragmento("4", "doc", {"requiere_revision_humana": "True"})

        resultado = filtrar_fragmentos_confiables([sucio])

        self.assertEqual(resultado, [])

    def test_todos_descartados_devuelve_lista_vacia(self):
        sucio_1 = _fragmento("3", "doc3", {"requiere_revision_humana": "true"})
        sucio_2 = _fragmento("4", "doc4", {"advertencias": '["texto repetido"]'})

        resultado = filtrar_fragmentos_confiables([sucio_1, sucio_2])

        self.assertEqual(resultado, [])

    def test_metadata_ausente_no_lanza_excepcion(self):
        fragmento_sin_metadata = {"contenido": "x", "coincidencia_lexica": 1.0}

        resultado = filtrar_fragmentos_confiables([fragmento_sin_metadata])

        self.assertEqual(resultado, [fragmento_sin_metadata])

    def test_campos_ausentes_en_metadata_no_lanzan_excepcion(self):
        # Caso real: doc 13 nunca tuvo estas claves en su metadata.
        limpio = _fragmento("13", "Manual limpio")

        resultado = filtrar_fragmentos_confiables([limpio])

        self.assertEqual(resultado, [limpio])

    def test_requiere_revision_humana_none_no_lanza_excepcion_y_pasa(self):
        fragmento = _fragmento("13", "doc", {"requiere_revision_humana": None, "advertencias": None})

        resultado = filtrar_fragmentos_confiables([fragmento])

        self.assertEqual(resultado, [fragmento])

    def test_advertencias_lista_vacia_no_descarta(self):
        fragmento = _fragmento("13", "doc", {"advertencias": []})

        resultado = filtrar_fragmentos_confiables([fragmento])

        self.assertEqual(resultado, [fragmento])

    def test_advertencias_string_json_vacio_no_descarta(self):
        fragmento = _fragmento("13", "doc", {"advertencias": "[]"})

        resultado = filtrar_fragmentos_confiables([fragmento])

        self.assertEqual(resultado, [fragmento])

    def test_requiere_revision_humana_bool_real_true_se_descarta(self):
        fragmento = _fragmento("4", "doc", {"requiere_revision_humana": True})

        resultado = filtrar_fragmentos_confiables([fragmento])

        self.assertEqual(resultado, [])

    def test_lista_vacia_de_entrada_devuelve_lista_vacia(self):
        self.assertEqual(filtrar_fragmentos_confiables([]), [])


@override_settings(CACHES={
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-conversacion-filtro-confiabilidad",
    }
})
class ApiConsultaIaFiltroConfiabilidadTests(SimpleTestCase):
    @patch("Bety_AI.views.buscar_fragmentos_con_fallback")
    @patch("Bety_AI.views.guardar_interaccion_temporal", return_value=[])
    @patch("Bety_AI.views.generar_respuesta_controlada")
    @patch("Bety_AI.views.interpretar_consulta_ia")
    def test_todos_los_fragmentos_no_confiables_responde_sin_informacion(
        self,
        interpretar_mock,
        respuesta_controlada_mock,
        guardar_temporal_mock,
        buscar_mock,
    ):
        interpretar_mock.return_value = {
            "tipo_operacion": "consulta_documental",
            "consulta_normalizada": "justificar inasistencia",
            "consulta_busqueda": "justificar inasistencia",
            "depende_historial": False,
            "formato_respuesta": "normal",
            "palabras_clave": [],
            "filtros_sugeridos": {},
            "modelo": "qwen-test",
        }
        buscar_mock.return_value = (
            [
                _fragmento(
                    "4",
                    "Guia matriculacion pregrado",
                    {"requiere_revision_humana": "true"},
                    contenido="contenido contaminado de matricula",
                )
            ],
            {},
        )
        respuesta_controlada_mock.return_value = {
            "respuesta": "No encontre informacion suficiente sobre eso.",
            "modelo": "qwen-control",
        }

        request = APIRequestFactory().post(
            "/api/ia/consulta/",
            {
                "pregunta": "Como justifico mi inasistencia?",
                "conversation_id": "convtest-filtro-confiable",
                "perfil": "Estudiante",
                "tipo_estudiante": "Pregrado",
                "carrera": "Software",
                "facultad": "FCC",
            },
            format="json",
        )
        request.session = type("SessionStub", (dict,), {})()

        response = api_consulta_ia(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["tipo_respuesta"], "FUERA_AMBITO")
        respuesta_controlada_mock.assert_called_once()
        self.assertEqual(
            obtener_ultimo_tipo_respuesta_conversacion("convtest-filtro-confiable"),
            "FUERA_AMBITO",
        )


class _ColeccionChromaFalsa:
    """Stub de la coleccion de chromadb.HttpClient para pruebas sin servidor real."""

    def __init__(self, documentos, metadatas, distancias):
        self._documentos = documentos
        self._metadatas = metadatas
        self._distancias = distancias

    def query(self, **kwargs):
        return {
            "documents": [self._documentos],
            "metadatas": [self._metadatas],
            "distances": [self._distancias],
        }


class RankingFragmentosChromaTests(SimpleTestCase):
    """
    Casos sinteticos para el fix de ranking de 2026-08-07 (ver memoria
    pending_ranking_lexico_no_escala). No se puede reproducir la colision con
    el corpus real actual (solo 2 documentos), asi que estos fragmentos se
    construyen a mano para simular el escenario del incidente de julio: dos
    documentos con vocabulario generico compartido (aqui, palabras de perfil
    filtradas hacia la busqueda), uno con titulo que gana por substring
    literal sin ser el correcto, y la pregunta apuntando al otro.
    """

    def test_calcular_score_ranking_combina_distancia_y_lexica_con_tope(self):
        # distancia manda; el ajuste por lexica nunca pasa de
        # PESO_LEXICO * LEXICA_MAXIMA_CONSIDERADA (0.1 * 3.0 = 0.3 con los
        # defaults), incluso si la coincidencia lexica cruda es mucho mayor.
        self.assertAlmostEqual(calcular_score_ranking(1.0, 0.0), 1.0)
        self.assertAlmostEqual(calcular_score_ranking(1.0, 3.0), 0.7)
        self.assertAlmostEqual(calcular_score_ranking(1.0, 999.0), 0.7)
        self.assertAlmostEqual(calcular_score_ranking(None, 1.0), 999999 - 0.1)

    def test_defaults_documentados_son_0_1_y_3_0(self):
        # Si esto falla, cambio el default sin querer: los valores
        # calibrados el 2026-08-07 deben quedar explicitos aqui.
        self.assertAlmostEqual(chroma_service.PESO_LEXICO, 0.1)
        self.assertAlmostEqual(chroma_service.LEXICA_MAXIMA_CONSIDERADA, 3.0)

    def test_son_configurables_por_variable_de_entorno(self):
        try:
            with patch.dict(
                os.environ,
                {
                    "CHROMA_PESO_LEXICO": "0.25",
                    "CHROMA_LEXICA_MAXIMA_CONSIDERADA": "5.0",
                },
            ):
                # El reload debe ocurrir DENTRO del patch.dict, para que
                # os.getenv() a nivel de modulo lea los valores parcheados.
                importlib.reload(chroma_service)
                self.assertAlmostEqual(chroma_service.PESO_LEXICO, 0.25)
                self.assertAlmostEqual(chroma_service.LEXICA_MAXIMA_CONSIDERADA, 5.0)
        finally:
            # El segundo reload debe ocurrir FUERA del patch.dict (env ya
            # restaurado), si no el modulo se queda con los valores
            # parcheados y contamina el resto de los tests de este archivo.
            importlib.reload(chroma_service)

        self.assertAlmostEqual(chroma_service.PESO_LEXICO, 0.1)
        self.assertAlmostEqual(chroma_service.LEXICA_MAXIMA_CONSIDERADA, 3.0)

    @patch("Bety_AI.services.chroma_service.obtener_coleccion")
    def test_colision_lexica_incidental_ya_no_gana_a_mejor_distancia_semantica(
        self, obtener_coleccion_mock
    ):
        """
        Reproduce el incidente de 2026-07-24: la pregunta arrastra palabras
        genericas de perfil ("estudiante", "pregrado", "periodo academico").
        El documento correcto (17, justificacion de inasistencias) no
        comparte esas palabras en su titulo -- solo tiene contenido
        relevante. El documento senuelo (20, guia de matriculacion) las
        tiene todas en el titulo (peso x3) pero su contenido no tiene nada
        que ver con la pregunta.

        Con el sort viejo (lexicografico: -lexica primero, distancia solo en
        empate exacto) el senuelo gana pese a tener peor distancia semantica
        -- eso es lo que fallo en produccion. Con el score combinado, la
        ventaja de distancia del documento correcto (0.90 vs 1.30, gap 0.40)
        supera el tope maximo que la coincidencia lexica puede corregir
        (0.3), y gana el documento correcto.
        """
        pregunta = (
            "Justificar inasistencia del estudiante de pregrado en el "
            "periodo academico"
        )

        titulo_correcto = "Manual de Justificacion de Inasistencias"
        contenido_correcto = (
            "Este documento describe el procedimiento para justificar una "
            "inasistencia. El estudiante debe presentar la solicitud "
            "dentro de las 72 horas siguientes."
        )
        titulo_senuelo = (
            "Guia de Matriculacion para Estudiantes de Pregrado - Periodo "
            "Academico 2026"
        )
        contenido_senuelo = (
            "Verifique la oferta academica, seleccione las asignaturas "
            "correspondientes y descargue el comprobante de matricula "
            "antes de la fecha limite del periodo academico."
        )

        obtener_coleccion_mock.return_value = _ColeccionChromaFalsa(
            documentos=[contenido_senuelo, contenido_correcto],
            metadatas=[
                {"id_documento": "20", "titulo": titulo_senuelo},
                {"id_documento": "17", "titulo": titulo_correcto},
            ],
            # distancias: correcto (17) semanticamente mas cercano (0.90)
            # que el senuelo (20, 1.30) -- gap de 0.40, del mismo orden que
            # el gap "tema distinto" observado en produccion.
            distancias=[1.30, 0.90],
        )

        fragmentos = chroma_service.buscar_fragmentos(pregunta, total_resultados=2)

        lexica_por_id = {f["metadata"]["id_documento"]: f["coincidencia_lexica"] for f in fragmentos}
        # Prueba de que el escenario es real: bajo el criterio viejo
        # (mayor coincidencia_lexica gana) el senuelo hubiera ganado.
        self.assertGreater(lexica_por_id["20"], lexica_por_id["17"])

        self.assertEqual(fragmentos[0]["metadata"]["id_documento"], "17")

    @patch("Bety_AI.services.chroma_service.obtener_coleccion")
    def test_empate_cerrado_de_distancia_lo_sigue_desempatando_lexica_fuerte(
        self, obtener_coleccion_mock
    ):
        """
        Contraparte del caso anterior: cuando la distancia semantica esta
        practicamente empatada (gap de 0.02, del mismo orden que el gap
        entre fragmentos del mismo documento observado en produccion) y un
        documento tiene una coincidencia lexica fuerte y genuina (match de
        titulo + contenido, no incidental), ese documento debe seguir
        ganando -- la red de seguridad lexica no debe romperse por el fix.
        """
        pregunta = "Manual para restablecer la contrasena del correo institucional"

        titulo_correcto = "Manual para Restablecer la Contrasena del Correo Institucional"
        contenido_correcto = (
            "Este manual explica como restablecer la contrasena del correo "
            "institucional desde el SGA."
        )
        titulo_debil = "Guia General del SGA"
        contenido_debil = "Puedes contactar por correo a soporte tecnico si tienes dudas."

        obtener_coleccion_mock.return_value = _ColeccionChromaFalsa(
            documentos=[contenido_correcto, contenido_debil],
            metadatas=[
                {"id_documento": "1", "titulo": titulo_correcto},
                {"id_documento": "9", "titulo": titulo_debil},
            ],
            distancias=[0.95, 0.97],
        )

        fragmentos = chroma_service.buscar_fragmentos(pregunta, total_resultados=2)

        lexica_por_id = {f["metadata"]["id_documento"]: f["coincidencia_lexica"] for f in fragmentos}
        self.assertGreater(lexica_por_id["1"], lexica_por_id["9"])

        self.assertEqual(fragmentos[0]["metadata"]["id_documento"], "1")


class PuntuarCoincidenciaLexicaCamposMuertosTests(SimpleTestCase):
    """
    Fix del 2026-08-12 (ver memoria pending_score_lexico_campos_ya_filtrados):
    puntuar_coincidencia_lexica dejo de puntuar metadata.perfil y
    metadata.ambito. Verificado que ambos campos nunca actuan como filtro de
    acceso en el flujo normal -- perfil (singular) porque el filtro real usa
    la clave "perfiles", no "perfil", y ambito porque construir_filtros_desde_
    perfil nunca lo setea. tipo_documento/perfiles/grupos/tipos_periodo se
    dejaron intactos a proposito: tipo_documento es señal de texto libre real
    y los otros tres solo filtran quedo condicionado al perfil del usuario.
    """

    def test_score_no_cambia_cuando_perfil_y_ambito_estan_vacios(self):
        pregunta = "requisitos para ser ayudante de catedra"
        texto = "El ayudante de catedra debe cumplir requisitos academicos."
        metadata = {"titulo": "Guia ayudante de catedra"}

        self.assertGreater(
            chroma_service.puntuar_coincidencia_lexica(pregunta, texto, metadata),
            0,
        )
        self.assertAlmostEqual(
            chroma_service.puntuar_coincidencia_lexica(pregunta, texto, metadata),
            chroma_service.puntuar_coincidencia_lexica(
                pregunta,
                texto,
                {**metadata, "perfil": "", "ambito": ""},
            ),
        )

    def test_score_baja_cuando_perfil_o_ambito_estaban_poblados(self):
        # metadata.perfil ya no se lee, asi que compararlo contra la misma
        # funcion con esos campos vacios (como en el test anterior) no puede
        # detectar una regresion: la funcion actual los ignora por diseño.
        # Para probar que el ruido realmente se fue, replicamos aqui la
        # formula vieja (con perfil/ambito sumando) y confirmamos que el
        # score actual queda por debajo de lo que esa formula habria dado.
        pregunta = "requisitos ayudante catedra estudiante"
        texto = "El ayudante de catedra debe cumplir requisitos academicos."
        metadata = {
            "titulo": "Guia ayudante de catedra",
            "perfil": "estudiante",
            "ambito": "estudiante academico",
        }

        tokens = chroma_service.extraer_tokens_busqueda(pregunta)
        perfil_normalizado = chroma_service.normalizar_texto(metadata["perfil"])
        ambito_normalizado = chroma_service.normalizar_texto(metadata["ambito"])
        coincidencias_perfil = sum(1 for token in tokens if token in perfil_normalizado)
        coincidencias_ambito = sum(1 for token in tokens if token in ambito_normalizado)
        # perfil pesaba x2, ambito x1 en la formula vieja (chroma_service.py:72-95).
        score_formula_vieja_con_ruido = chroma_service.puntuar_coincidencia_lexica(
            pregunta, texto, metadata
        ) + (coincidencias_perfil * 2 + coincidencias_ambito) / max(len(tokens), 1)

        score_actual = chroma_service.puntuar_coincidencia_lexica(pregunta, texto, metadata)

        self.assertGreater(coincidencias_perfil + coincidencias_ambito, 0)
        self.assertLess(score_actual, score_formula_vieja_con_ruido)

    def test_tipo_documento_perfiles_grupos_tipos_periodo_siguen_puntuando(self):
        pregunta = "reglamento estudiante software segundo periodo"
        texto = "Texto sin relacion literal con la pregunta."
        metadata = {
            "titulo": "Documento",
            "tipo_documento": "reglamento",
            "perfiles": "estudiante",
            "grupos": "software",
            "tipos_periodo": "segundo periodo",
        }

        self.assertGreater(
            chroma_service.puntuar_coincidencia_lexica(pregunta, texto, metadata),
            0,
        )


class PenalizacionNivelContrarioTests(SimpleTestCase):
    """
    Fix del 2026-08-07 (ver memoria pending_filtro_tipo_estudiante_bloquea_
    nivel_explicito): fragmento_contrario_a_tipo_estudiante dejo de excluir
    fragmentos del nivel academico contrario al perfil y paso a penalizar
    score_ranking. perfil/perfiles/grupos (rol real) NO cambiaron -- siguen
    siendo filtros duros en chroma_service.py, esto es solo sobre nivel
    academico (pregrado/posgrado), que nunca fue un permiso de acceso real.
    """

    def test_nivel_academico_fragmento_detecta_pregrado_posgrado_ambos_ninguno(self):
        self.assertEqual(
            nivel_academico_fragmento({"contenido": "informacion de pregrado", "metadata": {}}),
            "pregrado",
        )
        self.assertEqual(
            nivel_academico_fragmento({"contenido": "informacion de posgrado", "metadata": {}}),
            "posgrado",
        )
        self.assertEqual(
            nivel_academico_fragmento({"contenido": "pregrado y posgrado", "metadata": {}}),
            "ambos",
        )
        self.assertEqual(
            nivel_academico_fragmento({"contenido": "informacion general sin nivel", "metadata": {}}),
            "ninguno",
        )

    def test_calcular_penalizacion_nivel_contrario_solo_penaliza_nivel_opuesto(self):
        fragmento_posgrado = {"contenido": "informacion de posgrado", "metadata": {}}
        fragmento_pregrado = {"contenido": "informacion de pregrado", "metadata": {}}
        fragmento_general = {"contenido": "informacion general sin nivel", "metadata": {}}

        self.assertEqual(
            calcular_penalizacion_nivel_contrario(fragmento_posgrado, "pregrado"),
            busqueda_fragmentos_module.PENALIZACION_NIVEL_CONTRARIO,
        )
        self.assertEqual(
            calcular_penalizacion_nivel_contrario(fragmento_pregrado, "posgrado"),
            busqueda_fragmentos_module.PENALIZACION_NIVEL_CONTRARIO,
        )
        # Nivel del mismo lado, sin nivel, o sin tipo_estudiante: sin penalizacion.
        self.assertEqual(calcular_penalizacion_nivel_contrario(fragmento_pregrado, "pregrado"), 0.0)
        self.assertEqual(calcular_penalizacion_nivel_contrario(fragmento_general, "pregrado"), 0.0)
        self.assertEqual(calcular_penalizacion_nivel_contrario(fragmento_posgrado, ""), 0.0)

    def test_default_es_0_25(self):
        self.assertAlmostEqual(busqueda_fragmentos_module.PENALIZACION_NIVEL_CONTRARIO, 0.25)

    def test_configurable_por_variable_de_entorno(self):
        try:
            with patch.dict(os.environ, {"PENALIZACION_NIVEL_CONTRARIO": "0.5"}):
                importlib.reload(busqueda_fragmentos_module)
                self.assertAlmostEqual(busqueda_fragmentos_module.PENALIZACION_NIVEL_CONTRARIO, 0.5)
        finally:
            importlib.reload(busqueda_fragmentos_module)

        self.assertAlmostEqual(busqueda_fragmentos_module.PENALIZACION_NIVEL_CONTRARIO, 0.25)
