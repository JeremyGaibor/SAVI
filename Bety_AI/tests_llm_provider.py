import os
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError, ConnectTimeoutError, NoCredentialsError
from django.test import SimpleTestCase

from .services.llm_provider import (
    BedrockProvider,
    LLMProviderError,
    OllamaProvider,
    generar_texto,
    get_provider,
)


def _client_error(codigo):
    return ClientError({"Error": {"Code": codigo, "Message": "boom"}}, "Converse")


class OllamaProviderTests(SimpleTestCase):
    @patch("Bety_AI.services.llm_provider.requests.post")
    def test_generate_devuelve_texto_limpio(self, post_mock):
        post_mock.return_value = MagicMock(
            json=lambda: {"response": "  hola  ", "model": "qwen3:8b"},
            raise_for_status=lambda: None,
        )

        provider = OllamaProvider()
        texto = provider.generate("hola")

        self.assertEqual(texto, "hola")
        self.assertEqual(provider.model_name, "qwen3:8b")

    @patch("Bety_AI.services.llm_provider.requests.post")
    def test_generate_error_de_red_levanta_llm_provider_error(self, post_mock):
        import requests

        post_mock.side_effect = requests.ConnectionError("no se pudo conectar")

        provider = OllamaProvider()
        with self.assertRaises(LLMProviderError) as ctx:
            provider.generate("hola")

        self.assertEqual(ctx.exception.provider, "ollama")


class BedrockProviderTests(SimpleTestCase):
    @patch("Bety_AI.services.llm_provider.boto3.client")
    def test_generate_devuelve_texto_de_converse(self, client_factory_mock):
        cliente_mock = MagicMock()
        cliente_mock.converse.return_value = {
            "output": {"message": {"content": [{"text": "  respuesta ok  "}]}}
        }
        client_factory_mock.return_value = cliente_mock

        provider = BedrockProvider()
        texto = provider.generate("hola")

        self.assertEqual(texto, "respuesta ok")
        cliente_mock.converse.assert_called_once()
        _, kwargs = cliente_mock.converse.call_args
        self.assertEqual(kwargs["messages"], [{"role": "user", "content": [{"text": "hola"}]}])

    @patch("Bety_AI.services.llm_provider.boto3.client")
    def test_no_credentials_error_da_motivo_accionable(self, client_factory_mock):
        cliente_mock = MagicMock()
        cliente_mock.converse.side_effect = NoCredentialsError()
        client_factory_mock.return_value = cliente_mock

        provider = BedrockProvider()
        with self.assertRaises(LLMProviderError) as ctx:
            provider.generate("hola")

        self.assertIn("IAM Role", ctx.exception.motivo)
        self.assertIn("hop limit", ctx.exception.motivo)

    @patch("Bety_AI.services.llm_provider.boto3.client")
    def test_throttling_exception_da_motivo_accionable(self, client_factory_mock):
        cliente_mock = MagicMock()
        cliente_mock.converse.side_effect = _client_error("ThrottlingException")
        client_factory_mock.return_value = cliente_mock

        provider = BedrockProvider()
        with self.assertRaises(LLMProviderError) as ctx:
            provider.generate("hola")

        self.assertIn("limite de tasa", ctx.exception.motivo)

    @patch("Bety_AI.services.llm_provider.boto3.client")
    def test_access_denied_exception_da_motivo_accionable(self, client_factory_mock):
        cliente_mock = MagicMock()
        cliente_mock.converse.side_effect = _client_error("AccessDeniedException")
        client_factory_mock.return_value = cliente_mock

        provider = BedrockProvider()
        with self.assertRaises(LLMProviderError) as ctx:
            provider.generate("hola")

        self.assertIn("IAM Role", ctx.exception.motivo)
        self.assertIn("bedrock:InvokeModel", ctx.exception.motivo)

    @patch("Bety_AI.services.llm_provider.boto3.client")
    def test_validation_exception_da_motivo_accionable(self, client_factory_mock):
        cliente_mock = MagicMock()
        cliente_mock.converse.side_effect = _client_error("ValidationException")
        client_factory_mock.return_value = cliente_mock

        provider = BedrockProvider()
        with self.assertRaises(LLMProviderError) as ctx:
            provider.generate("hola")

        self.assertIn("BEDROCK_MODEL_ID", ctx.exception.motivo)

    @patch("Bety_AI.services.llm_provider.boto3.client")
    def test_timeout_da_motivo_accionable(self, client_factory_mock):
        cliente_mock = MagicMock()
        cliente_mock.converse.side_effect = ConnectTimeoutError(endpoint_url="https://bedrock")
        client_factory_mock.return_value = cliente_mock

        provider = BedrockProvider()
        with self.assertRaises(LLMProviderError) as ctx:
            provider.generate("hola")

        self.assertIn("timeout", ctx.exception.motivo)

    @patch("Bety_AI.services.llm_provider.boto3.client")
    def test_respuesta_con_formato_inesperado_levanta_error(self, client_factory_mock):
        cliente_mock = MagicMock()
        cliente_mock.converse.return_value = {"output": {}}
        client_factory_mock.return_value = cliente_mock

        provider = BedrockProvider()
        with self.assertRaises(LLMProviderError):
            provider.generate("hola")


class GetProviderTests(SimpleTestCase):
    def test_proveedor_desconocido_levanta_error(self):
        with self.assertRaises(LLMProviderError):
            get_provider("no-existe")


class GenerarTextoFallbackTests(SimpleTestCase):
    @patch.dict("os.environ", {"LLM_PROVIDER": "ollama", "LLM_FALLBACK_PROVIDER": ""}, clear=False)
    @patch("Bety_AI.services.llm_provider.OllamaProvider")
    def test_primario_exitoso_no_usa_fallback(self, ollama_cls_mock):
        instancia = MagicMock(model_name="qwen3:8b")
        instancia.generate.return_value = "respuesta"
        ollama_cls_mock.return_value = instancia

        resultado = generar_texto("hola")

        self.assertEqual(resultado["respuesta"], "respuesta")
        self.assertEqual(resultado["proveedor"], "ollama")

    @patch.dict("os.environ", {"LLM_PROVIDER": "ollama", "LLM_FALLBACK_PROVIDER": ""}, clear=False)
    @patch("Bety_AI.services.llm_provider.BedrockProvider")
    @patch("Bety_AI.services.llm_provider.OllamaProvider")
    def test_primario_falla_sin_fallback_configurado_propaga_error(self, ollama_cls_mock, bedrock_cls_mock):
        instancia = MagicMock()
        instancia.generate.side_effect = LLMProviderError("ollama", "caido")
        ollama_cls_mock.return_value = instancia

        with self.assertRaises(LLMProviderError):
            generar_texto("hola")

        bedrock_cls_mock.assert_not_called()

    @patch.dict("os.environ", {"LLM_PROVIDER": "ollama"}, clear=False)
    @patch("Bety_AI.services.llm_provider.BedrockProvider")
    @patch("Bety_AI.services.llm_provider.OllamaProvider")
    def test_fallback_no_definida_en_entorno_se_trata_como_sin_fallback(self, ollama_cls_mock, bedrock_cls_mock):
        # Simula el caso real de GitHub Actions: el secret LLM_FALLBACK_PROVIDER
        # no existe en absoluto (no solo vacio), como cuando nunca se crea el
        # secret porque GitHub no permite secrets con valor vacio.
        os.environ.pop("LLM_FALLBACK_PROVIDER", None)

        instancia = MagicMock()
        instancia.generate.side_effect = LLMProviderError("ollama", "caido")
        ollama_cls_mock.return_value = instancia

        with self.assertRaises(LLMProviderError):
            generar_texto("hola")

        bedrock_cls_mock.assert_not_called()

    @patch.dict("os.environ", {"LLM_PROVIDER": "ollama", "LLM_FALLBACK_PROVIDER": "   "}, clear=False)
    @patch("Bety_AI.services.llm_provider.BedrockProvider")
    @patch("Bety_AI.services.llm_provider.OllamaProvider")
    def test_fallback_solo_espacios_se_trata_como_sin_fallback(self, ollama_cls_mock, bedrock_cls_mock):
        instancia = MagicMock()
        instancia.generate.side_effect = LLMProviderError("ollama", "caido")
        ollama_cls_mock.return_value = instancia

        with self.assertRaises(LLMProviderError):
            generar_texto("hola")

        bedrock_cls_mock.assert_not_called()

    @patch.dict("os.environ", {"LLM_PROVIDER": "ollama", "LLM_FALLBACK_PROVIDER": "bedrock"}, clear=False)
    @patch("Bety_AI.services.llm_provider.BedrockProvider")
    @patch("Bety_AI.services.llm_provider.OllamaProvider")
    def test_primario_falla_usa_fallback(self, ollama_cls_mock, bedrock_cls_mock):
        ollama_instancia = MagicMock()
        ollama_instancia.generate.side_effect = LLMProviderError("ollama", "caido")
        ollama_cls_mock.return_value = ollama_instancia

        bedrock_instancia = MagicMock(model_name="amazon.nova-lite-v1:0")
        bedrock_instancia.generate.return_value = "respuesta de bedrock"
        bedrock_cls_mock.return_value = bedrock_instancia

        resultado = generar_texto("hola")

        self.assertEqual(resultado["respuesta"], "respuesta de bedrock")
        self.assertEqual(resultado["proveedor"], "bedrock")

    @patch.dict("os.environ", {"LLM_PROVIDER": "ollama", "LLM_FALLBACK_PROVIDER": "ollama"}, clear=False)
    @patch("Bety_AI.services.llm_provider.OllamaProvider")
    def test_fallback_igual_al_primario_se_trata_como_sin_fallback(self, ollama_cls_mock):
        instancia = MagicMock()
        instancia.generate.side_effect = LLMProviderError("ollama", "caido")
        ollama_cls_mock.return_value = instancia

        with self.assertRaises(LLMProviderError):
            generar_texto("hola")

        # Solo debio construirse una vez (para el intento primario), no un
        # segundo intento contra si mismo.
        self.assertEqual(ollama_cls_mock.call_count, 1)

    @patch.dict("os.environ", {"LLM_PROVIDER": "ollama", "LLM_FALLBACK_PROVIDER": "bedrock"}, clear=False)
    @patch("Bety_AI.services.llm_provider.BedrockProvider")
    @patch("Bety_AI.services.llm_provider.OllamaProvider")
    def test_ambos_proveedores_fallan_propaga_error_del_fallback(self, ollama_cls_mock, bedrock_cls_mock):
        ollama_instancia = MagicMock()
        ollama_instancia.generate.side_effect = LLMProviderError("ollama", "caido")
        ollama_cls_mock.return_value = ollama_instancia

        bedrock_instancia = MagicMock()
        bedrock_instancia.generate.side_effect = LLMProviderError("bedrock", "tambien caido")
        bedrock_cls_mock.return_value = bedrock_instancia

        with self.assertRaises(LLMProviderError) as ctx:
            generar_texto("hola")

        self.assertEqual(ctx.exception.provider, "bedrock")
