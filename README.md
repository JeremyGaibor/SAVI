# SAVI – Sistema de Asistencia Virtual Inteligente

SAVI es un asistente documental desarrollado para facilitar la consulta de información institucional mediante una interfaz conversacional. El sistema recupera contexto relevante desde documentos indexados antes de generar una respuesta, utilizando un flujo RAG (Retrieval-Augmented Generation).

## Funcionalidades principales

- Chatbot web utilizable directamente o mediante `iframe`.
- Procesamiento y análisis de documentos PDF.
- Extracción de texto y métricas de legibilidad.
- Fragmentación e indexación de documentos en ChromaDB.
- Recuperación semántica y ranking de fragmentos para RAG.
- Manejo de sesiones y contexto mediante Redis.
- Integración con servicios del SGA mediante `sessionid`.
- Actualización de enlaces asociados a versiones documentales.
- Retiro de versiones documentales que ya no se encuentran vigentes.
- Soporte para modelos locales mediante Ollama y modelos en AWS Bedrock.
- Despliegue mediante Docker, Gunicorn y Nginx.

## Tecnologías

- Python 3.11
- Django 5
- Django REST Framework
- ChromaDB
- Redis
- SQLite
- Ollama
- AWS Bedrock
- Docker / Docker Compose
- Gunicorn
- Nginx
- GitHub Actions

## Estructura principal

```text
SAVI/
├── .github/
│   └── workflows/          # Automatización de despliegue
├── app/                    # Configuración principal del proyecto
├── assistant/              # Chatbot, RAG, procesamiento e integraciones
├── docs/                   # Documentación del proyecto
├── .env.example            # Plantilla de variables de entorno
├── API_INTEGRACION_DOCUMENTOS.md
├── Dockerfile
├── docker-compose.yml
├── manage.py
└── requirements.txt
```

## Requisitos

Para ejecutar el proyecto mediante Docker se requiere:

- Docker Engine
- Docker Compose v2
- Acceso al proveedor de IA seleccionado
- Variables de entorno configuradas

Para ejecución local sin Docker se requiere Python 3.11 y las dependencias definidas en `requirements.txt`.

## Configuración

Crear el archivo `.env` a partir de la plantilla:

```bash
cp .env.example .env
```

Completar únicamente con valores válidos para el entorno correspondiente.

Las principales variables de configuración incluyen:

```env
OLLAMA_BASE_URL=
OLLAMA_MODEL=
OLLAMA_TIMEOUT_SECONDS=

LLM_PROVIDER=
LLM_FALLBACK_PROVIDER=

BEDROCK_MODEL_ID=
AWS_REGION=
BEDROCK_CONNECT_TIMEOUT_SECONDS=
BEDROCK_READ_TIMEOUT_SECONDS=

CHROMA_HOST=
CHROMA_PORT=
CHROMA_COLLECTION=

REDIS_URL=

SGA_API_TOKEN_URL=
SGA_API_USUARIO_SESION_URL=
SGA_API_TOKEN_FIJO=
SGA_API_USUARIO=
SGA_API_PASSWORD=

DOCUMENT_FRAGMENTATION_MODE=
```

> No deben almacenarse credenciales, contraseñas, tokens ni secretos reales en el repositorio.

## Ejecución con Docker

Construir y levantar los servicios:

```bash
docker compose up -d --build
```

Verificar el estado:

```bash
docker compose ps
```

Consultar los logs de la aplicación:

```bash
docker compose logs -f savi
```

La configuración actual de Docker Compose utiliza los servicios:

- `savi_app`: aplicación Django ejecutada con Gunicorn.
- `savi_chroma`: almacenamiento vectorial ChromaDB.
- `savi_redis`: sesiones y caché.

La aplicación se publica localmente en:

```text
127.0.0.1:8000
```

En producción, Nginx actúa como proxy inverso y gestiona el acceso HTTPS.

## Ejecución local

Crear un entorno virtual:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Instalar dependencias:

```bash
pip install -r requirements.txt
```

Aplicar migraciones:

```bash
python manage.py migrate
```

Ejecutar el servidor de desarrollo:

```bash
python manage.py runserver
```

## Proveedores de inteligencia artificial

SAVI permite seleccionar el proveedor mediante:

```env
LLM_PROVIDER=ollama
```

o:

```env
LLM_PROVIDER=bedrock
```

### Ollama

Requiere configurar:

```env
OLLAMA_BASE_URL=
OLLAMA_MODEL=
OLLAMA_TIMEOUT_SECONDS=
```

### AWS Bedrock

Requiere configurar:

```env
BEDROCK_MODEL_ID=
AWS_REGION=
```

La autenticación de AWS debe gestionarse mediante mecanismos seguros del entorno de ejecución, evitando almacenar credenciales dentro del repositorio.

## Persistencia

SAVI utiliza tres mecanismos principales:

- **SQLite:** datos propios de Django.
- **ChromaDB:** fragmentos, embeddings y metadatos documentales.
- **Redis:** sesiones, caché y datos temporales.

Docker Compose utiliza volúmenes persistentes para SQLite y ChromaDB.

## Integración documental

La integración de documentos incluye operaciones para:

- analizar documentos;
- guardar contenido procesado en ChromaDB;
- actualizar el enlace de una versión documental;
- retirar una versión documental de la búsqueda.

La especificación técnica de estos servicios se encuentra en:

```text
API_INTEGRACION_DOCUMENTOS.md
```

## Flujo general

```text
Usuario
  ↓
Chatbot web / iframe
  ↓
Nginx
  ↓
Aplicación Django
  ↓
Sesión y contexto
  ↓
Búsqueda RAG en ChromaDB
  ↓
Proveedor IA (Ollama / AWS Bedrock)
  ↓
Respuesta al usuario
```

Para documentos:

```text
Sistema documental
  ↓
API de integración
  ↓
Extracción y análisis
  ↓
Fragmentación
  ↓
ChromaDB
```

## Pruebas

El proyecto contempla pruebas funcionales y de integración sobre:

- consultas del chatbot;
- análisis de PDF;
- almacenamiento documental;
- recuperación mediante RAG;
- separación de sesiones;
- integración con el SGA;
- actualización y retiro de documentos;
- acceso mediante `iframe`;
- rendimiento y estabilidad.

Después de una modificación importante se recomienda volver a ejecutar los casos críticos y comprobar los logs de la aplicación.

## Despliegue

El despliegue se realiza con Docker y Gunicorn. La imagen de la aplicación expone el puerto `8000` internamente y Docker Compose lo enlaza a `127.0.0.1:8000`.

En producción:

1. Clonar la rama `main`.
2. Crear `.env` desde `.env.example`.
3. Configurar las variables requeridas.
4. Ejecutar:

```bash
docker compose pull
docker compose up -d
```

5. Verificar:

```bash
docker compose ps
```

6. Configurar Nginx como proxy inverso hacia `127.0.0.1:8000`.
7. Habilitar HTTPS.
8. Probar el chatbot y sus integraciones.

## Respaldo

Los elementos principales que deben respaldarse son:

- volumen de ChromaDB;
- volumen de SQLite;
- configuración de Nginx;
- archivo `.env`, únicamente mediante un canal seguro.

Los secretos no deben almacenarse dentro de copias públicas del repositorio.

## Seguridad

- El acceso de producción debe realizarse mediante HTTPS.
- ChromaDB y Redis no deben exponerse directamente a Internet.
- Las credenciales deben configurarse mediante variables de entorno.
- `.env` no debe versionarse.
- `.env.example` debe contener únicamente placeholders.
- Cualquier credencial que haya sido publicada previamente debe ser rotada.

## Documentación adicional

- `API_INTEGRACION_DOCUMENTOS.md`: contrato de integración documental.
- `docs/`: documentación complementaria del proyecto.
- Documento Técnico de Ingeniería de Software y Continuidad del Producto: arquitectura, requisitos, pruebas, despliegue, mantenimiento y continuidad.

## Continuidad del proyecto

Antes de realizar nuevos cambios se recomienda:

1. Verificar que la rama `main` esté actualizada.
2. Configurar el entorno a partir de `.env.example`.
3. Levantar los servicios con Docker Compose.
4. Confirmar conectividad con Redis, ChromaDB, proveedor IA y servicios del SGA.
5. Ejecutar las pruebas funcionales críticas.
6. Revisar la deuda técnica y los pendientes documentados.

## Autores

- Jeremy Ruperto Gaibor Rodríguez
- Andy Paul Sánchez Pilaloa

Proyecto desarrollado durante prácticas preprofesionales de la Carrera de Ingeniería de Software de la Universidad Técnica Estatal de Quevedo.
