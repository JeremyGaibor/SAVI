from django.core.management.base import BaseCommand

from Bety_AI.services.llm_provider import BedrockProvider, LLMProviderError


class Command(BaseCommand):
    help = (
        "Prueba de conectividad con AWS Bedrock (API Converse). "
        "Reporta si el fallo es de credenciales, region o model ID."
    )

    def handle(self, *args, **options):
        try:
            provider = BedrockProvider()
        except Exception as exc:
            self.stderr.write(
                self.style.ERROR(f"No se pudo construir el cliente de Bedrock (revisar AWS_REGION): {exc}")
            )
            return

        self.stdout.write(f"Probando Bedrock -> modelo={provider.model_name} region={provider.region}")

        try:
            texto = provider.generate("Responde unicamente con la palabra: ok")
        except LLMProviderError as exc:
            self.stderr.write(self.style.ERROR(f"Fallo la conexion con Bedrock -> {exc.motivo}"))
            return
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Error inesperado no mapeado: {exc}"))
            return

        self.stdout.write(self.style.SUCCESS(f"Bedrock OK. Respuesta del modelo: {texto!r}"))
