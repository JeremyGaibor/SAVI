# API de integracion documental

Base local de desarrollo:

```text
http://127.0.0.1:8000
```

## 1. Analizar documento

Extrae texto del PDF, calcula metricas de legibilidad y sugiere metadatos con IA.

```http
POST /api/integracion/documentos/analizar/
Content-Type: multipart/form-data
```

Campo requerido:

- `archivo`: PDF a analizar.

Ejemplo:

```bash
curl -X POST http://127.0.0.1:8000/api/integracion/documentos/analizar/ \
  -F "archivo=@documento.pdf"
```

Respuesta principal:

- `estado_extraccion`: `EXTRAIDO` o `ERROR`.
- `texto_extraido`: texto completo extraido del PDF.
- `titulo_sugerido`, `tipo_documento_sugerido`, `perfil_sugerido`, `carrera_sugerida`.
- `resumen`, `temas_detectados`, `advertencias`.
- `paginas`, `caracteres_extraidos`, `requiere_revision`, `analisis_paginas`.

## 2. Guardar en ChromaDB

Guarda el documento en la base vectorial de SAVI. No requiere que el documento exista en una base local nuestra; el `id_documento` puede ser el ID externo del sistema documental.

```http
POST /api/integracion/documentos/guardar-chroma/
```

Puede recibirse de dos formas:

- `multipart/form-data` con `archivo` PDF.
- `application/json` con `texto_extraido`, por ejemplo el texto devuelto por la API de analisis.

Campos requeridos:

- `id_documento`: identificador externo unico del documento.
- `archivo` o `texto_extraido`: contenido que se va a fragmentar e indexar.

Campos opcionales:

- `titulo`: titulo final del documento. Si no se envia, SAVI usa `metadata.titulo`, `metadata.nombre_archivo` o `Documento {id_documento}`.
- `accion_chroma`: usar `reemplazar_version_vigente` cuando el sistema documental envia una version nueva que reemplaza otra vigente.
- `id_version`
- `uuid_documento`
- `uuid_version`
- `id_version_anterior`
- `uuid_version_anterior`: UUID de la version que debe eliminarse de Chroma antes de indexar la nueva.
- `estado_vigencia`
- `anio_documento`
- `tipo_documento`
- `resumen_documento`
- `temas_detectados`
- `nombre_archivo`
- `metadata`: objeto JSON con metadatos documentales permitidos.
- `reemplazar_existente`: `true` por defecto. Con `accion_chroma=reemplazar_version_vigente` y `uuid_version_anterior`, borra los fragmentos de esa version anterior. Si no se envia `uuid_version_anterior`, mantiene el comportamiento anterior y borra por `id_documento`.

Campos permitidos dentro de `metadata`:

- `numero_version`
- `numero_version_anterior`
- `archivo_path`
- `documento_url`: enlace que debe abrirse cuando el chatbot muestra la fuente del documento.
- `tipo_documento`
- `perfiles`
- `grupos`
- `tipos_periodo`
- `resumen_documento`

Para filtrado documental, SAVI guarda los nombres en campos simples de lista:

- `perfiles`: uno o varios nombres de perfil.
- `grupos`: uno o varios nombres de grupo/facultad.
- `tipos_periodo`: uno o varios nombres de tipo de periodo. Si se envia `tipo_periodo`, se toma como alias y se guarda como `tipos_periodo`.

El guardado ignora campos tecnicos de legibilidad y campos simples o no confirmados, aunque se envien en `metadata`, por ejemplo:

- `porcentaje_texto`
- `porcentaje_imagenes`
- `advertencias`
- `requiere_revision_humana`
- `perfil`
- `grupo`
- `periodo`
- `carrera`
- `tipo_estudio`
- `fuente`
- `temas_detectados`
- `ambito`
- `perfiles_acceso`
- `id_perfil_externo`
- `grupos_acceso`
- `id_grupo_externo`
- `tipos_periodo_acceso`
- `id_tipo_periodo_externo`

Configuracion de fragmentacion:

- `DOCUMENT_FRAGMENTATION_MODE=pages`: guarda un fragmento por pagina. Es el modo por defecto.
- `DOCUMENT_FRAGMENTATION_MODE=caracteres1200`: guarda por cantidad de caracteres, como antes, usando fragmentos de hasta 1200 caracteres.

Cuando se usa `pages`, cada fragmento guarda tambien `pagina_inicio` y `pagina_fin` en la metadata de ChromaDB.

Ejemplo usando PDF:

```bash
curl -X POST http://127.0.0.1:8000/api/integracion/documentos/guardar-chroma/ \
  -F "id_documento=DOC-123" \
  -F "titulo=Manual de matricula" \
  -F "tipo_documento=MANUAL" \
  -F "perfil=ESTUDIANTE" \
  -F "periodo=2026-S1" \
  -F "archivo=@documento.pdf"
```

Ejemplo usando texto ya analizado:

```bash
curl -X POST http://127.0.0.1:8000/api/integracion/documentos/guardar-chroma/ \
  -H "Content-Type: application/json" \
  -d '{
    "id_documento": "DOC-123",
    "titulo": "Manual de matricula",
    "tipo_documento": "MANUAL",
    "perfil": "ESTUDIANTE",
    "periodo": "2026-S1",
    "texto_extraido": "Contenido completo del documento...",
    "metadata": {
      "sistema_origen": "grupo_documentos"
    }
  }'
```

Ejemplo reemplazando la version vigente por UUID:

```bash
curl -X POST http://127.0.0.1:8000/api/integracion/documentos/guardar-chroma/ \
  -H "Content-Type: application/json" \
  -d '{
    "accion_chroma": "reemplazar_version_vigente",
    "id_documento": "123",
    "id_version": "45",
    "uuid_documento": "uuid-del-documento",
    "uuid_version": "uuid-version-nueva",
    "id_version_anterior": "44",
    "uuid_version_anterior": "uuid-version-anterior",
    "reemplazar_existente": true,
    "texto_extraido": "Contenido completo de la nueva version...",
    "metadata": {
      "id_documento": "123",
      "id_version": "45",
      "numero_version": "3",
      "perfil": "ESTUDIANTE",
      "periodo": "2026-S1",
      "uuid_documento": "uuid-del-documento",
      "uuid_version": "uuid-version-nueva",
      "id_version_anterior": "44",
      "numero_version_anterior": "2",
      "uuid_version_anterior": "uuid-version-anterior"
    }
  }'
```

Respuesta principal:

- `estado_procesamiento`: `PROCESADO`, `PENDIENTE_OCR` o `ERROR`.
- `fragmentos_generados`: cantidad de fragmentos guardados en ChromaDB.
- `modo_fragmentacion`: `pages` o `characters`, segun la configuracion aplicada.
- `reemplazo_fragmentos_previos`: indica si se borraron fragmentos anteriores del mismo documento.
- `reemplazo_por_uuid_anterior`: `true` cuando la eliminacion se hizo por `uuid_version_anterior`.
- `uuid_version_anterior_eliminada`: UUID de la version anterior eliminada cuando aplica.
- `requiere_ocr`: `true` cuando no hay texto suficiente para indexar.

## 3. Actualizar link del documento

Agrega o reemplaza el link final del documento en todos los fragmentos de una version ya guardada en ChromaDB. Se usa cuando el sistema documental todavia no tenia el enlace en el momento de llamar a `guardar-chroma`.

```http
POST /api/integracion/documentos/actualizar-link/
Content-Type: application/json
```

Campos requeridos:

- `uuid_version`: UUID de la version exacta que se debe actualizar.
- `documento_url`: URL `http(s)` o ruta relativa que debe abrirse al hacer clic en la fuente del chatbot.

Ejemplo:

```bash
curl -X POST http://127.0.0.1:8000/api/integracion/documentos/actualizar-link/ \
  -H "Content-Type: application/json" \
  -d '{
    "uuid_version": "uuid-version-actual",
    "documento_url": "https://sistema-documental.uteq.edu.ec/documentos/123/versiones/45"
  }'
```

Respuesta principal:

- `estado_procesamiento`: `LINK_ACTUALIZADO`, `NO_ENCONTRADO` o `ERROR`.
- `fragmentos_actualizados`: cantidad de fragmentos de esa version actualizados.
- `documento_url`: link guardado en la metadata.

Cuando el chatbot devuelve fuentes, la respuesta incluye el campo `url` pero el frontend muestra el nombre del documento como texto clickeable, no la URL.

## 4. Quitar vigencia en ChromaDB

Elimina de la base vectorial los fragmentos de una version que ya no esta vigente. No analiza PDF, no extrae texto y no registra una version nueva.

```http
POST /api/integracion/documentos/quitar-vigencia/
Content-Type: application/json
```

Campo requerido:

- `uuid_version`: UUID de la version que debe dejar de estar disponible para busqueda.

Ejemplo:

```bash
curl -X POST http://127.0.0.1:8000/api/integracion/documentos/quitar-vigencia/ \
  -H "Content-Type: application/json" \
  -d '{
    "uuid_version": "uuid-version-que-ya-no-esta-vigente"
  }'
```

Respuesta principal:

- `estado_procesamiento`: `VIGENCIA_QUITADA` o `ERROR`.
- `uuid_version`: UUID eliminado de ChromaDB.
