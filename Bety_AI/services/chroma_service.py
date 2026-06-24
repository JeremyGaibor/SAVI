import chromadb


CHROMA_HOST = "localhost"
CHROMA_PORT = 8001
COLLECTION_NAME = "bety_ai_documentos"


def obtener_coleccion():
    client = chromadb.HttpClient(
        host=CHROMA_HOST,
        port=CHROMA_PORT
    )

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME
    )

    return collection


def guardar_fragmentos_documento(
    id_documento,
    titulo,
    fragmentos,
    metadata_base
):
    """
    Guarda fragmentos en ChromaDB.
    Por ahora dejamos que Chroma genere embeddings automáticamente.
    """
    collection = obtener_coleccion()

    ids = []
    documents = []
    metadatas = []

    for indice, fragmento in enumerate(fragmentos, start=1):
        id_fragmento = f"doc_{id_documento}_frag_{indice}"

        metadata = metadata_base.copy()
        metadata["id_documento"] = str(id_documento)
        metadata["titulo"] = titulo
        metadata["numero_fragmento"] = indice

        ids.append(id_fragmento)
        documents.append(fragmento)
        metadatas.append(metadata)

    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas
    )

    return len(ids)

def construir_where_chroma(filtros):
    """
    Convierte filtros simples de Django a formato válido para ChromaDB.
    Si hay un filtro:
        {"ambito": "PUBLICO"}
    Si hay varios:
        {"$and": [{"ambito": "PUBLICO"}, {"rol": "ESTUDIANTE"}]}
    """
    if not filtros:
        return None

    condiciones = []

    for clave, valor in filtros.items():
        if valor not in [None, ""]:
            condiciones.append({clave: valor})

    if not condiciones:
        return None

    if len(condiciones) == 1:
        return condiciones[0]

    return {"$and": condiciones}


def buscar_fragmentos(pregunta, filtros=None, total_resultados=3):
    """
    Busca fragmentos relevantes en ChromaDB usando similitud semántica.
    """
    collection = obtener_coleccion()

    where = construir_where_chroma(filtros)

    resultados = collection.query(
        query_texts=[pregunta],
        n_results=total_resultados,
        where=where,
        include=["documents", "metadatas", "distances"]
    )

    documentos = resultados.get("documents", [[]])[0]
    metadatas = resultados.get("metadatas", [[]])[0]
    distancias = resultados.get("distances", [[]])[0]

    fragmentos = []

    for texto, metadata, distancia in zip(documentos, metadatas, distancias):
        fragmentos.append({
            "contenido": texto,
            "metadata": metadata,
            "distancia": distancia
        })

    return fragmentos