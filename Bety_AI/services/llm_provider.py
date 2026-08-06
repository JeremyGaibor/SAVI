import logging
import os

import boto3
import requests
from botocore.config import Config
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    NoCredentialsError,
    ReadTimeoutError,
)

logger = logging.getLogger("Bety_AI.llm_provider")


class LLMProviderError(Exception):
    """Error de un proveedor LLM con un motivo accionable, solo para logs/diagnostico."""

    def __init__(self, provider, motivo):
        self.provider = provider
        self.motivo = motivo
        super().__init__(f"[{provider}] {motivo}")


class LLMProvider:
    model_name = ""

    def generate(self, prompt, context=""):
        raise NotImplementedError


class OllamaProvider(LLMProvider):
    def __init__(self):
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        self.model_name = os.getenv("OLLAMA_MODEL", "qwen3:8b")
        self.timeout_seconds = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))

    def generate(self, prompt, context=""):
        url = f"{self.base_url}/api/generate"
        texto_prompt = f"{context}\n{prompt}" if context else prompt

        # stream=False simplifica el consumo desde Django porque Ollama responde
        # un solo JSON con el texto completo generado por el modelo.
        # think=False es necesario porque qwen3 es un modelo hibrido de razonamiento:
        # si no se desactiva, Ollama puede devolver el bloque de pensamiento interno
        # mezclado dentro de "response", lo que se percibe como 2 respuestas seguidas.
        payload = {
            "model": self.model_name,
            "prompt": texto_prompt,
            "stream": False,
            "think": False,
        }

        try:
            response = requests.post(url, json=payload, timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise LLMProviderError("ollama", f"error de conexion con Ollama ({exc})") from exc

        data = response.json()
        self.model_name = data.get("model") or self.model_name
        return (data.get("response") or "").strip()


class BedrockProvider(LLMProvider):
    # Codigos de error de la API Converse (botocore ClientError) con su causa
    # accionable mas probable. Referencia: la API Converse se autoriza con la
    # accion IAM "bedrock:InvokeModel" (no existe "bedrock:Converse").
    _CODIGOS_ACCIONABLES = {
        "ThrottlingException": "limite de tasa (throttling) de Bedrock alcanzado, reintenta mas tarde o revisa cuotas",
        "AccessDeniedException": (
            "acceso denegado: revisar que el IAM Role de la instancia tenga la accion "
            "bedrock:InvokeModel y que el modelo este habilitado (model access) en la region configurada"
        ),
        "ValidationException": "solicitud invalida: revisar BEDROCK_MODEL_ID y AWS_REGION",
    }

    def __init__(self):
        self.model_name = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
        self.region = os.getenv("AWS_REGION", "us-east-2")
        connect_timeout = int(os.getenv("BEDROCK_CONNECT_TIMEOUT_SECONDS", "5"))
        read_timeout = int(os.getenv("BEDROCK_READ_TIMEOUT_SECONDS", "60"))

        # Sin credenciales explicitas: boto3 usa su cadena de credenciales por
        # defecto (IAM Role adjunto a la instancia EC2 via IMDS).
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=self.region,
            config=Config(connect_timeout=connect_timeout, read_timeout=read_timeout),
        )

    def generate(self, prompt, context=""):
        texto_prompt = f"{context}\n{prompt}" if context else prompt

        try:
            response = self._client.converse(
                modelId=self.model_name,
                messages=[{"role": "user", "content": [{"text": texto_prompt}]}],
            )
        except NoCredentialsError as exc:
            raise LLMProviderError(
                "bedrock",
                "sin credenciales AWS: revisar que la instancia EC2 tenga un IAM Role adjunto y que el "
                "hop limit del servicio de metadatos (IMDS) sea >=2 (Docker agrega un salto de red adicional)",
            ) from exc
        except (ConnectTimeoutError, ReadTimeoutError, EndpointConnectionError) as exc:
            raise LLMProviderError(
                "bedrock", f"timeout o problema de conectividad de red hacia Bedrock ({exc})"
            ) from exc
        except ClientError as exc:
            codigo = exc.response.get("Error", {}).get("Code", "")
            motivo = self._CODIGOS_ACCIONABLES.get(codigo, f"error de Bedrock (codigo={codigo or 'desconocido'})")
            raise LLMProviderError("bedrock", motivo) from exc

        try:
            return response["output"]["message"]["content"][0]["text"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError("bedrock", f"respuesta de Bedrock con formato inesperado ({exc})") from exc


def get_provider(nombre):
    # Se resuelve por nombre de clase a nivel de modulo (no via un dict armado
    # en import-time) para que los tests puedan sustituir OllamaProvider/
    # BedrockProvider con @patch sin que get_provider siga apuntando a la
    # clase original ya capturada.
    nombre_normalizado = (nombre or "").strip().lower()
    if nombre_normalizado == "ollama":
        return OllamaProvider()
    if nombre_normalizado == "bedrock":
        return BedrockProvider()
    raise LLMProviderError(nombre or "(vacio)", "proveedor LLM desconocido")


def generar_texto(prompt, context=""):
    """
    Genera texto usando el proveedor de LLM_PROVIDER, con fallback opcional a
    LLM_FALLBACK_PROVIDER (vacio = sin fallback) si el primario falla. El
    fallback se intenta una sola vez, nunca reintenta indefinidamente.
    """
    proveedor_primario = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
    proveedor_fallback = os.getenv("LLM_FALLBACK_PROVIDER", "").strip().lower()

    try:
        provider = get_provider(proveedor_primario)
        texto = provider.generate(prompt, context)
        logger.info("LLM: '%s' (modelo=%s) respondio la consulta", proveedor_primario, provider.model_name)
        return {"respuesta": texto, "modelo": provider.model_name, "proveedor": proveedor_primario}
    except Exception as exc:
        if not proveedor_fallback or proveedor_fallback == proveedor_primario:
            logger.error("LLM: '%s' fallo y no hay fallback configurado (%s)", proveedor_primario, exc)
            raise

        logger.warning(
            "LLM: '%s' fallo (%s), intentando fallback '%s'", proveedor_primario, exc, proveedor_fallback
        )
        try:
            provider_fallback = get_provider(proveedor_fallback)
            texto = provider_fallback.generate(prompt, context)
            logger.info(
                "LLM: fallback '%s' (modelo=%s) respondio la consulta tras fallo de '%s'",
                proveedor_fallback,
                provider_fallback.model_name,
                proveedor_primario,
            )
            return {"respuesta": texto, "modelo": provider_fallback.model_name, "proveedor": proveedor_fallback}
        except Exception as exc2:
            logger.error(
                "LLM: fallback '%s' tambien fallo (%s); '%s' (primario) habia fallado por (%s)",
                proveedor_fallback,
                exc2,
                proveedor_primario,
                exc,
            )
            raise
