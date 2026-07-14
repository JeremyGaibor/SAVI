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
- `titulo_sugerido`, `tipo_documento_sugerido`, `rol_sugerido`, `carrera_sugerida`.
- `resumen`, `temas_detectados`, `advertencias`.
- `paginas`, `caracteres_extraidos`, `requiere_revision`, `analisis_paginas`.

## 2. Guardar en ChromaDB

Guarda el documento en la base vectorial de Bety-AI. No requiere que el documento exista en una base local nuestra; el `id_documento` puede ser el ID externo del sistema documental.

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

- `titulo`: titulo final del documento. Si no se envia, Bety-AI usa `metadata.titulo`, `metadata.nombre_archivo` o `Documento {id_documento}`.
- `accion_chroma`: usar `reemplazar_version_vigente` cuando el sistema documental envia una version nueva que reemplaza otra vigente.
- `id_version`
- `uuid_documento`
- `uuid_version`
- `id_version_anterior`
- `uuid_version_anterior`: UUID de la version que debe eliminarse de Chroma antes de indexar la nueva.
- `tipo_documento`
- `ambito`
- `estado_vigencia`
- `anio_documento`
- `rol`
- `carrera`
- `grupo`
- `tipo_estudio`
- `resumen_documento`
- `temas_detectados`
- `advertencias`
- `requiere_revision_humana`
- `nombre_archivo`
- `metadata`: objeto JSON con metadatos adicionales.
- `reemplazar_existente`: `true` por defecto. Con `accion_chroma=reemplazar_version_vigente` y `uuid_version_anterior`, borra los fragmentos de esa version anterior. Si no se envia `uuid_version_anterior`, mantiene el comportamiento anterior y borra por `id_documento`.

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
  -F "rol=ESTUDIANTE" \
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
    "rol": "ESTUDIANTE",
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
