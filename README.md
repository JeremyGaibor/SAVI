# SAVI – Sistema de Asistencia Virtual Inteligente

SAVI es un asistente documental desarrollado para facilitar la consulta de información institucional mediante una interfaz conversacional. El sistema recupera información relevante desde documentos indexados y la utiliza como contexto antes de generar una respuesta mediante un flujo RAG (*Retrieval-Augmented Generation*).

## Estado actual

El proyecto dispone de un entorno piloto de validación desplegado en AWS. Este entorno no se considera una integración institucional en producción con el Sistema de Gestión Académica (SGA).

El repositorio incluye un cliente y un flujo por `sessionid` para solicitar contexto del usuario a servicios del SGA. Esta funcionalidad se ha comprobado mediante pruebas controladas; la conexión, validación y aceptación institucional definitivas con el SGA permanecen pendientes.

El flujo de despliegue vigente configura el dominio:

```text
https://saviuteq.duckdns.org/chatbot/
```

## Funcionalidades principales

- Chatbot web accesible directamente o mediante `iframe`.
- Procesamiento y análisis de documentos PDF.
- Extracción de texto y cálculo de métricas de legibilidad.
- Fragmentación e indexación de documentos en ChromaDB.
- Recuperación semántica y ranking de fragmentos para RAG.
- Separación de conversaciones por sesión.
- Uso de Redis para caché y sesiones.
- Cliente de contexto por `sessionid` para la futura integración institucional con el SGA.
- Actualización de enlaces asociados a versiones documentales.
- Retiro de versiones documentales que dejan de estar vigentes.
- Proveedores de inteligencia artificial configurables: Ollama y AWS Bedrock.
- Ejecución mediante Docker, Gunicorn y Nginx.
- Construcción y despliegue automatizados mediante GitHub Actions.

## Tecnologías principales

- Python 3.11.
- Django 5.0.
- Django REST Framework 3.17.1.
- Cliente Python ChromaDB 1.5.9.
- Servidor ChromaDB mediante la imagen `chromadb/chroma:latest`.
- Redis 7 Alpine y cliente Python Redis 5.0.1.
- SQLite.
- Ollama.
- AWS Bedrock mediante Boto3 1.43.64.
- Docker y Docker Compose.
- Gunicorn 23.0.0.
- Nginx.
- GitHub Actions.

Las versiones completas de las dependencias de Python se encuentran en `requirements.txt`.

## Estructura del repositorio

```text
SAVI/
├── .github/
│   └── workflows/
│       └── deploy.yml                # Construcción y despliegue automatizados
├── app/                              # Aplicación funcional de SAVI
│   ├── management/                   # Comandos de administración
│   ├── migrations/                   # Migraciones de la aplicación
│   ├── services/                     # Servicios de PDF y ChromaDB
│   ├── static/                       # Recursos estáticos
│   ├── templates/                    # Interfaz web del chatbot
│   ├── view_logic/                   # RAG, documentos, contexto y respuestas
│   ├── tests.py                      # Pruebas de la aplicación
│   ├── tests_llm_provider.py         # Pruebas de proveedores de IA
│   ├── urls.py                       # Rutas de SAVI
│   └── views.py                      # Vistas y endpoints
├── assistant/                        # Configuración del proyecto Django
│   ├── settings.py                   # Configuración general
│   ├── urls.py                       # Enrutamiento principal
│   ├── asgi.py                       # Entrada ASGI
│   └── wsgi.py                       # Entrada WSGI para Gunicorn
├── docs/
│   └── pruebas_estres_ia.md          # Evidencia y notas de pruebas de estrés
├── .env.example                      # Plantilla de variables de entorno
├── API_INTEGRACION_DOCUMENTOS.md     # Especificación de la API documental
├── MANUAL DE USUARIO.pdf             # Manual de uso de SAVI
├── Dockerfile                        # Imagen de la aplicación
├── docker-compose.yml                # Servicios SAVI, ChromaDB y Redis
├── manage.py                         # Utilidad de administración de Django
└── requirements.txt                  # Dependencias de Python
```

## Requisitos

Para ejecutar SAVI con Docker se requiere:

- Docker Engine.
- Docker Compose v2.
- Acceso al proveedor de inteligencia artificial seleccionado.
- Variables de entorno configuradas.

Para ejecutarlo sin Docker se requiere Python 3.11 y las dependencias definidas en `requirements.txt`.

## Configuración

Crear el archivo `.env` a partir de la plantilla:

```bash
cp .env.example .env
```

Completar los valores correspondientes al entorno. El archivo `.env` no debe añadirse al repositorio.

Las principales variables son:

```env
DEBUG=
ALLOWED_HOSTS=
CSRF_TRUSTED_ORIGINS=
SESSION_COOKIE_SECURE=
CSRF_COOKIE_SECURE=

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

No deben almacenarse contraseñas, tokens, credenciales ni secretos reales en el repositorio.

## Ejecución con Docker

Construir y levantar los servicios:

```bash
docker compose up -d --build
```

Verificar su estado:

```bash
docker compose ps
```

Consultar los logs:

```bash
docker compose logs -f savi
docker compose logs -f chromadb
docker compose logs -f redis
```

Los servicios definidos en `docker-compose.yml` son:

- `savi`: aplicación Django ejecutada en el contenedor `savi_app`.
- `chromadb`: servidor vectorial ejecutado en `savi_chroma`.
- `redis`: caché y sesiones ejecutadas en `savi_redis`.

La aplicación se enlaza localmente a:

```text
127.0.0.1:8000
```

ChromaDB y Redis solo se exponen dentro de la red de contenedores.

## Ejecución local

Crear y activar un entorno virtual:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Instalar dependencias y aplicar migraciones:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
```

Iniciar el servidor de desarrollo:

```bash
python manage.py runserver
```

El servidor estará disponible en `http://127.0.0.1:8000/`.

## Proveedores de inteligencia artificial

Seleccionar el proveedor principal mediante `LLM_PROVIDER`:

```env
LLM_PROVIDER=ollama
```

o:

```env
LLM_PROVIDER=bedrock
```

El proveedor alternativo se configura con `LLM_FALLBACK_PROVIDER`. Puede dejarse vacío si no se necesita conmutación.

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
BEDROCK_CONNECT_TIMEOUT_SECONDS=
BEDROCK_READ_TIMEOUT_SECONDS=
```

La autenticación de AWS debe gestionarse mediante un rol IAM u otro mecanismo seguro del entorno. Las credenciales no deben almacenarse en el repositorio.

## Persistencia

SAVI utiliza:

- **SQLite:** datos propios de Django, persistidos en el volumen `sqlite_data`.
- **ChromaDB:** fragmentos, embeddings y metadatos documentales, persistidos en `chroma_data`.
- **Redis:** sesiones, caché y datos temporales. El servicio actual no define un volumen persistente.

## Rutas y endpoints

### Interfaz

- `GET /chatbot/`: abre el chatbot web.
- `GET /chatbot/<sessionid>/`: abre el chatbot con un identificador de sesión para el flujo de contexto.
- `GET /chroma_dump.html`: muestra la interfaz de consulta y administración de ChromaDB.

### API documental principal

- `POST /api/integracion/documentos/analizar/`: analiza un documento.
- `POST /api/integracion/documentos/guardar-chroma/`: procesa e indexa contenido en ChromaDB.
- `POST` o `PATCH /api/integracion/documentos/actualizar-link/`: actualiza el enlace de una versión documental.
- `POST` o `DELETE /api/integracion/documentos/quitar-vigencia/`: retira una versión documental de la búsqueda.

La especificación de campos, respuestas y modos de fragmentación se encuentra en `API_INTEGRACION_DOCUMENTOS.md`.

### Otras rutas disponibles

- `/api/legibilidad/`
- `/api/documentos/procesar/`
- `/api/ia/buscar/`
- `/chat/buscar/`
- `/api/ia/consulta/`
- `/api/documentos/analizar/`
- `/api/documentos/extraer-texto/`

Algunas de estas rutas se conservan como alias de compatibilidad.

## Flujo general

```text
Usuario
  ↓
Chatbot web o iframe
  ↓
Nginx
  ↓
Aplicación Django
  ↓
Sesión y recuperación de contexto
  ↓
Búsqueda RAG en ChromaDB
  ↓
Proveedor de IA: Ollama o AWS Bedrock
  ↓
Respuesta al usuario
```

Flujo documental:

```text
Sistema consumidor
  ↓
API de integración documental
  ↓
Extracción y análisis
  ↓
Fragmentación
  ↓
ChromaDB
```

El cliente del SGA puede solicitar token y contexto por `sessionid` cuando se configuran las variables correspondientes. Esto no implica que la integración institucional definitiva ya haya sido completada.

## Pruebas

Ejecutar las pruebas disponibles con:

```bash
python manage.py test app
```

El repositorio contiene pruebas y evidencias relacionadas con:

- consultas del chatbot;
- análisis de PDF;
- recuperación mediante RAG;
- proveedores de IA;
- sesiones y flujo por `sessionid` en condiciones controladas;
- actualización y retiro de versiones documentales;
- acceso mediante `iframe`;
- estabilidad y latencia.

Las pruebas controladas del cliente por `sessionid` no sustituyen la validación con los servicios institucionales reales del SGA.

## Despliegue piloto

El workflow `.github/workflows/deploy.yml` se ejecuta al actualizar la rama `main` o mediante activación manual. El proceso:

1. Descarga el código.
2. Construye la imagen de SAVI.
3. Publica las etiquetas `latest` y `${{ github.sha }}` en Docker Hub.
4. Sincroniza los archivos con `/home/ubuntu/SAVI` en el runner autorizado.
5. Genera el `.env` del servidor desde secretos de GitHub Actions.
6. Descarga las imágenes definidas en Docker Compose.
7. Ejecuta las migraciones.
8. Inicia los servicios y muestra su estado.

Para una instalación manual:

```bash
git clone https://github.com/JeremyGaibor/SAVI.git
cd SAVI
cp .env.example .env
# Completar .env por un canal seguro.
docker compose pull
docker compose run --rm savi python manage.py migrate
docker compose up -d --remove-orphans
docker compose ps
```

Nginx debe actuar como proxy inverso hacia `127.0.0.1:8000` y gestionar HTTPS. El entorno actualmente documentado es de piloto/validación, no de producción institucional.

## Respaldo y restauración

Se deben respaldar:

- el volumen `chroma_data`;
- el volumen `sqlite_data`;
- el archivo `.env` mediante un canal seguro;
- la configuración de Nginx y los certificados, según la política institucional.

La restauración debe probarse y documentarse antes de considerar cerrado el procedimiento de recuperación.

## Seguridad y pendientes conocidos

- Mantener `.env` fuera del control de versiones.
- Conservar únicamente valores de ejemplo en `.env.example`.
- No publicar tokens, contraseñas, claves ni credenciales.
- Mantener ChromaDB y Redis sin exposición directa a Internet.
- Utilizar HTTPS y cookies seguras en el entorno desplegado.
- Migrar `SECRET_KEY` de Django desde `assistant/settings.py` a una variable de entorno y utilizar una clave diferente en el servidor.
- Unificar el dominio configurado en el código y el workflow mediante variables de entorno; el workflow vigente utiliza `saviuteq.duckdns.org`.
- Rotar inmediatamente cualquier credencial que haya sido expuesta.

## Documentación relacionada

- `API_INTEGRACION_DOCUMENTOS.md`: contrato de la API documental.
- `MANUAL DE USUARIO.pdf`: instrucciones de uso.
- `docs/pruebas_estres_ia.md`: información de las pruebas de estrés con proveedores de IA.

## Autores

- Jeremy Ruperto Gaibor Rodríguez.
- Andy Paul Sánchez Pilaloa.
