 import html
import json
from datetime import datetime
from pathlib import Path

from Bety_AI.services.chroma_service import (
    CHROMA_HOST,
    CHROMA_PORT,
    COLLECTION_NAME,
    obtener_coleccion,
)


SALIDA = Path(__file__).resolve().parent / "chroma_dump.html"


def recortar(texto, limite=1400):
    texto = str(texto or "")
    if len(texto) <= limite:
        return texto

    return texto[:limite].rstrip() + "..."


def valor_metadata(metadata, clave):
    valor = (metadata or {}).get(clave, "")
    if valor in [None, ""]:
        return "-"
    return str(valor)


def construir_reporte(ids, documentos, metadatas, error=None):
    filas = []
    resumen_documentos = {}

    for indice, item_id in enumerate(ids):
        metadata = metadatas[indice] if indice < len(metadatas) else {}
        documento = documentos[indice] if indice < len(documentos) else ""
        id_documento = valor_metadata(metadata, "id_documento")
        titulo = valor_metadata(metadata, "titulo")

        resumen_documentos.setdefault(id_documento, {
            "titulo": titulo,
            "fragmentos": 0,
            "tipo_documento": valor_metadata(metadata, "tipo_documento"),
            "rol": valor_metadata(metadata, "rol"),
            "carrera": valor_metadata(metadata, "carrera"),
            "estado_vigencia": valor_metadata(metadata, "estado_vigencia"),
        })
        resumen_documentos[id_documento]["fragmentos"] += 1

        metadata_json = json.dumps(metadata or {}, ensure_ascii=False, indent=2)

        filas.append(f"""
            <tr>
                <td>{indice + 1}</td>
                <td><code>{html.escape(str(item_id))}</code></td>
                <td>{html.escape(titulo)}</td>
                <td>{html.escape(valor_metadata(metadata, "tipo_documento"))}</td>
                <td>{html.escape(valor_metadata(metadata, "rol"))}</td>
                <td>{html.escape(valor_metadata(metadata, "carrera"))}</td>
                <td>{html.escape(valor_metadata(metadata, "estado_vigencia"))}</td>
                <td><pre>{html.escape(metadata_json)}</pre></td>
                <td><pre>{html.escape(recortar(documento))}</pre></td>
            </tr>
        """)

    documentos_html = []
    for id_documento, datos in resumen_documentos.items():
        documentos_html.append(f"""
            <tr>
                <td><code>{html.escape(id_documento)}</code></td>
                <td>{html.escape(datos["titulo"])}</td>
                <td>{html.escape(datos["tipo_documento"])}</td>
                <td>{html.escape(datos["rol"])}</td>
                <td>{html.escape(datos["carrera"])}</td>
                <td>{html.escape(datos["estado_vigencia"])}</td>
                <td>{datos["fragmentos"]}</td>
            </tr>
        """)

    estado = "OK" if error is None else "ERROR"
    error_html = ""
    if error:
        error_html = f"""
            <section class="error">
                <h2>No se pudo leer ChromaDB</h2>
                <pre>{html.escape(str(error))}</pre>
            </section>
        """

    return f"""<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <title>Contenido de ChromaDB - Bety-AI</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 24px;
            background: #f4f6f8;
            color: #1f2933;
        }}
        h1, h2 {{
            margin-bottom: 8px;
        }}
        .panel {{
            background: #fff;
            border: 1px solid #d8dee6;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 18px;
        }}
        .meta {{
            display: grid;
            grid-template-columns: repeat(4, minmax(160px, 1fr));
            gap: 10px;
        }}
        .dato {{
            background: #eef2f6;
            padding: 10px;
            border-radius: 6px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: #fff;
        }}
        th, td {{
            border: 1px solid #d8dee6;
            padding: 8px;
            vertical-align: top;
            text-align: left;
        }}
        th {{
            background: #e8edf3;
            position: sticky;
            top: 0;
        }}
        pre {{
            white-space: pre-wrap;
            word-break: break-word;
            max-width: 520px;
            margin: 0;
            font-size: 12px;
        }}
        code {{
            font-size: 12px;
        }}
        .error {{
            border-left: 5px solid #b83232;
        }}
    </style>
</head>
<body>
    <h1>Contenido de ChromaDB - Bety-AI</h1>

    <section class="panel meta">
        <div class="dato"><strong>Estado</strong><br>{estado}</div>
        <div class="dato"><strong>Host</strong><br>{html.escape(str(CHROMA_HOST))}:{CHROMA_PORT}</div>
        <div class="dato"><strong>Colección</strong><br>{html.escape(COLLECTION_NAME)}</div>
        <div class="dato"><strong>Generado</strong><br>{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
        <div class="dato"><strong>Fragmentos</strong><br>{len(ids)}</div>
        <div class="dato"><strong>Documentos</strong><br>{len(resumen_documentos)}</div>
    </section>

    {error_html}

    <section class="panel">
        <h2>Resumen por documento</h2>
        <table>
            <thead>
                <tr>
                    <th>ID documento</th>
                    <th>Título</th>
                    <th>Tipo</th>
                    <th>Rol</th>
                    <th>Carrera</th>
                    <th>Vigencia</th>
                    <th>Fragmentos</th>
                </tr>
            </thead>
            <tbody>
                {''.join(documentos_html)}
            </tbody>
        </table>
    </section>

    <section class="panel">
        <h2>Fragmentos guardados</h2>
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>ID fragmento</th>
                    <th>Título</th>
                    <th>Tipo</th>
                    <th>Rol</th>
                    <th>Carrera</th>
                    <th>Vigencia</th>
                    <th>Metadatos</th>
                    <th>Contenido</th>
                </tr>
            </thead>
            <tbody>
                {''.join(filas)}
            </tbody>
        </table>
    </section>
</body>
</html>
"""


def main():
    ids = []
    documentos = []
    metadatas = []
    error = None

    try:
        collection = obtener_coleccion()
        resultado = collection.get(include=["documents", "metadatas"])
        ids = resultado.get("ids", [])
        documentos = resultado.get("documents", [])
        metadatas = resultado.get("metadatas", [])
    except Exception as exc:
        error = exc

    SALIDA.write_text(
        construir_reporte(ids, documentos, metadatas, error=error),
        encoding="utf-8",
    )
    print(SALIDA)


if __name__ == "__main__":
    main()
