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
- `titulo`: titulo final del documento.
- `archivo` o `texto_extraido`: contenido que se va a fragmentar e indexar.

Campos opcionales:

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
- `reemplazar_existente`: `true` por defecto. Si ya existe ese `id_documento`, borra sus fragmentos previos antes de guardar.

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

Respuesta principal:

- `estado_procesamiento`: `PROCESADO`, `PENDIENTE_OCR` o `ERROR`.
- `fragmentos_generados`: cantidad de fragmentos guardados en ChromaDB.
- `reemplazo_fragmentos_previos`: indica si se borraron fragmentos anteriores del mismo documento.
- `requiere_ocr`: `true` cuando no hay texto suficiente para indexar.
