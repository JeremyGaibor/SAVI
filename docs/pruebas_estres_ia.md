# Pruebas de estres para la IA

El endpoint principal para medir el comportamiento de la IA es:

```text
POST /api/ia/consulta/
```

La prueba incluida en `scripts/stress_test_ia.py` mide el flujo completo: Django, sesion, Redis/cache de conversacion, ChromaDB y proveedor LLM configurado por `LLM_PROVIDER`.

## Ejecutar local

Primero levanta la aplicacion y sus dependencias. Con Docker Compose:

```powershell
docker compose up -d
```

Luego ejecuta una carga moderada:

```powershell
.\.venv\Scripts\python.exe scripts\stress_test_ia.py --base-url http://127.0.0.1:8000 --total 30 --concurrency 5
```

Si se ejecuta dentro del servidor y Django devuelve `400 Bad Request` por `ALLOWED_HOSTS`, conserva la conexion local pero envia el host publico permitido:

```bash
python3 ~/stress_test_ia.py --base-url http://127.0.0.1:8000 --host-header 16.58.71.138 --total 30 --concurrency 5
```

Para una prueba mas fuerte:

```powershell
.\.venv\Scripts\python.exe scripts\stress_test_ia.py --base-url http://127.0.0.1:8000 --total 100 --concurrency 10 --output-json reports/stress-ia.json
```

## Ejecutar contra servidor

```powershell
.\.venv\Scripts\python.exe scripts\stress_test_ia.py --base-url https://TU-DOMINIO-O-IP --total 100 --concurrency 10
```

Si el servidor usa la IP configurada en `assistant/settings.py`, verifica que `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS` permitan el host usado en `--base-url`.

## Criterios sugeridos

- `success_rate` >= 95%.
- Sin errores `5xx`.
- `p95` menor que el timeout real del LLM.
- Sin `ERROR_CHROMA` ni respuestas de IA no disponible bajo carga baja o media.

Tambien se puede hacer fallar el comando automaticamente:

```powershell
.\.venv\Scripts\python.exe scripts\stress_test_ia.py --total 50 --concurrency 5 --min-success-rate 98 --max-p95-ms 60000
```

## Leer resultados

El resumen imprime:

- `success_rate`: porcentaje de requests HTTP 2xx sin `ok=false`.
- `requests_per_second`: rendimiento observado.
- `latency_ms.p50/p95/p99`: latencias percentiles.
- `by_status`: distribucion HTTP.
- `by_tipo_respuesta`: tipos devueltos por la app.
- `by_modelo`: modelo que respondio.
- `sample_failures`: primeras fallas con status, latencia y error.

Para estresar conversaciones reales, usa `--conversation-mode shared` o `--conversation-mode per-worker`. El modo por defecto, `unique`, crea una conversacion nueva por consulta y exige mas escrituras de cache.
