import chromadb
import os
import re
import unicodedata
from dotenv import load_dotenv


load_dotenv()

# Estos valores salen de Bety-AI/.env. En desarrollo Chroma corre en Docker
# y se expone normalmente como localhost:8001.
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8001"))
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "bety_ai_documentos")

STOPWORDS = {
    "sobre", "para", "como", "cual", "cuales", "donde", "cuando", "quien",
    "quiero", "ayuda", "ayudame", "hablame", "dime", "del", "los", "las",
    "una", "uno", "unos", "unas", "con", "por", "que", "este", "esta",
    "documento", "proceso", "informacion"
}

SINONIMOS_CONSULTA = {
    "matriculacion": {"matricula", "matricular", "matriculas"},
    "matricula": {"matriculacion", "matricular", "matriculas"},
    "evaluativo": {"evaluacion", "evaluar", "evaluaciones", "calificar", "calificacion"},
    "evaluacion": {"evaluativo", "evaluar", "evaluaciones", "calificar", "calificacion"},
    "evaluar": {"evaluacion", "evaluaciones", "calificar", "calificacion"},
    "calificar": {"evaluar", "evaluacion", "evaluaciones", "heteroevaluacion", "hetero"},
    "calificacion": {"evaluar", "evaluacion", "evaluaciones", "heteroevaluacion", "hetero"},
    "heteroevaluacion": {"hetero", "evaluacion", "evaluar", "calificar"},
    "hetero": {"heteroevaluacion", "evaluacion", "evaluar", "calificar"},
    "profesor": {"profesores", "docente", "docentes", "ingeniero", "ingenieros"},
    "profesores": {"profesor", "docente", "docentes", "ingeniero", "ingenieros"},
    "docente": {"docentes", "profesor", "profesores", "ingeniero", "ingenieros"},
    "docentes": {"docente", "profesor", "profesores", "ingeniero", "ingenieros"},
    "ingeniero": {"ingenieros", "docente", "docentes", "profesor", "profesores"},
    "ingenieros": {"ingeniero", "docente", "docentes", "profesor", "profesores"},
    "grado": {"graduacion", "titulacion"},
    "titulacion": {"grado", "graduacion"},
}


def normalizar_texto(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    return texto.lower()


def extraer_tokens_busqueda(texto):
    tokens = set(re.findall(r"[a-z0-9]+", normalizar_texto(texto)))
    tokens = {token for token in tokens if len(token) > 3 and token not in STOPWORDS}

    expandidos = set(tokens)
    for token in tokens:
        expandidos.update(SINONIMOS_CONSULTA.get(token, set()))

    return expandidos


def construir_consulta_expandida(pregunta):
    """
    Agrega sinonimos de dominio a la consulta enviada a ChromaDB.

    Esto ayuda cuando el usuario usa palabras locales o equivalentes
    que no aparecen igual en el PDF, por ejemplo docente/profesor/ingeniero.
    """
    tokens = extraer_tokens_busqueda(pregunta)

    if not tokens:
        return pregunta

    return f"{pregunta} {' '.join(sorted(tokens))}"


def puntuar_coincidencia_lexica(pregunta, texto, metadata):
    tokens = extraer_tokens_busqueda(pregunta)

    if not tokens:
        return 0

    contenido = normalizar_texto(texto)
    titulo = normalizar_texto(metadata.get("titulo", ""))
    tipo_documento = normalizar_texto(metadata.get("tipo_documento", ""))
    rol = normalizar_texto(metadata.get("rol", ""))
    ambito = normalizar_texto(metadata.get("ambito", ""))

    coincidencias_contenido = sum(1 for token in tokens if token in contenido)
    coincidencias_titulo = sum(1 for token in tokens if token in titulo)
    coincidencias_tipo = sum(1 for token in tokens if token in tipo_documento)
    coincidencias_rol = sum(1 for token in tokens if token in rol)
    coincidencias_ambito = sum(1 for token in tokens if token in ambito)

    return (
        coincidencias_contenido
        + (coincidencias_titulo * 3)
        + (coincidencias_tipo * 2)
        + (coincidencias_rol * 2)
        + coincidencias_ambito
    ) / max(len(tokens), 1)


def obtener_coleccion():
    """
    Crea el cliente HTTP de ChromaDB y devuelve la coleccion documental.

    get_or_create_collection permite que el primer procesamiento cree la
    coleccion si todavia no existe en el contenedor Docker.
    """
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
        if isinstance(fragmento, dict):
            contenido = str(fragmento.get("contenido") or "")
            pagina_inicio = fragmento.get("pagina_inicio")
            pagina_fin = fragmento.get("pagina_fin")
        else:
            contenido = str(fragmento)
            pagina_inicio = None
            pagina_fin = None

        # Los metadatos permiten filtrar despues por rol, carrera, vigencia,
        # tipo de documento u otros criterios enviados por el sistema externo.
        metadata = metadata_base.copy()
        metadata["id_documento"] = str(id_documento)
        metadata["titulo"] = titulo
        metadata["numero_fragmento"] = indice
        if pagina_inicio is not None:
            metadata["pagina_inicio"] = int(pagina_inicio)
        if pagina_fin is not None:
            metadata["pagina_fin"] = int(pagina_fin)

        ids.append(id_fragmento)
        documents.append(contenido)
        metadatas.append(metadata)

    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas
    )

    return len(ids)


def listar_fragmentos_chroma():
    collection = obtener_coleccion()
    resultados = collection.get(include=["documents", "metadatas"])

    ids = resultados.get("ids", [])
    documentos = resultados.get("documents", [])
    metadatas = resultados.get("metadatas", [])

    fragmentos = []
    for indice, item_id in enumerate(ids):
        fragmentos.append({
            "id": item_id,
            "contenido": documentos[indice] if indice < len(documentos) else "",
            "metadata": metadatas[indice] if indice < len(metadatas) else {},
        })

    return fragmentos


def obtener_fragmento_chroma(id_fragmento):
    collection = obtener_coleccion()
    resultados = collection.get(
        ids=[id_fragmento],
        include=["documents", "metadatas"],
    )

    ids = resultados.get("ids", [])
    if not ids:
        return None

    documentos = resultados.get("documents", [])
    metadatas = resultados.get("metadatas", [])

    return {
        "id": ids[0],
        "contenido": documentos[0] if documentos else "",
        "metadata": metadatas[0] if metadatas else {},
    }


def crear_fragmento_chroma(id_fragmento, contenido, metadata):
    collection = obtener_coleccion()
    collection.add(
        ids=[id_fragmento],
        documents=[contenido],
        metadatas=[metadata],
    )


def actualizar_fragmento_chroma(id_fragmento, contenido, metadata):
    collection = obtener_coleccion()
    collection.update(
        ids=[id_fragmento],
        documents=[contenido],
        metadatas=[metadata],
    )


def eliminar_fragmento_chroma(id_fragmento):
    collection = obtener_coleccion()
    collection.delete(ids=[id_fragmento])


def eliminar_documento_chroma(id_documento):
    collection = obtener_coleccion()
    collection.delete(where={"id_documento": str(id_documento)})


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

    # Chroma devuelve documentos, metadatos y distancia de similitud.
    # Bety-AI usa estos fragmentos como contexto para la respuesta de Qwen.
    total_candidatos = max(total_resultados, 8)

    consulta_expandida = construir_consulta_expandida(pregunta)

    resultados = collection.query(
        query_texts=[consulta_expandida],
        n_results=total_candidatos,
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
            "distancia": distancia,
            "coincidencia_lexica": puntuar_coincidencia_lexica(pregunta, texto, metadata),
        })

    fragmentos.sort(
        key=lambda item: (
            -item["coincidencia_lexica"],
            item["distancia"] if item["distancia"] is not None else 999999,
        )
    )

    return fragmentos[:total_resultados]
