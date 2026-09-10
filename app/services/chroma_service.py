import chromadb
import json
import logging
import os
import re
import unicodedata
from dotenv import load_dotenv


load_dotenv()

logger = logging.getLogger("app.chroma_service")

# Estos valores salen de SAVI/.env. En desarrollo Chroma corre en Docker
# y se expone normalmente como localhost:8001.
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8001"))
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "documentos_institucionales")
FILTROS_LISTA_METADATA = {"perfiles", "grupos", "tipos_periodo"}

# perfiles es un permiso de acceso, no una senal de relevancia (ver
# busqueda_fragmentos.py). Estos valores marcan un documento como visible
# para cualquier perfil, incluido "sin perfil declarado".
PERFILES_ACCESO_PUBLICO = {"todos", "general", "publico", "publica"}

# Controlan cuanto puede la coincidencia lexica (substring literal) corregir
# el ranking por distancia semantica al combinarse en un score final. Ver
# buscar_fragmentos(). Calibrados el 2026-08-07 con un corpus real de solo
# 2 documentos: se esperan ajustes por variable de entorno (no por commit)
# a medida que el corpus crezca y haya mas datos de colisiones reales.
PESO_LEXICO = float(os.getenv("CHROMA_PESO_LEXICO", "0.1"))
LEXICA_MAXIMA_CONSIDERADA = float(os.getenv("CHROMA_LEXICA_MAXIMA_CONSIDERADA", "3.0"))

STOPWORDS = {
    "sobre", "para", "como", "cual", "cuales", "donde", "cuando", "quien",
    "quiero", "ayuda", "ayudame", "hablame", "dime", "del", "los", "las",
    "una", "uno", "unos", "unas", "con", "por", "que", "este", "esta",
    "documento", "proceso", "informacion"
}

def normalizar_texto(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    return texto.lower()


def extraer_tokens_busqueda(texto):
    tokens = set(re.findall(r"[a-z0-9]+", normalizar_texto(texto)))
    return {token for token in tokens if len(token) > 3 and token not in STOPWORDS}


def construir_consulta_expandida(pregunta):
    """
    Agrega tokens tecnicos de la consulta enviada a ChromaDB.

    La expansion semantica de sinonimos la hace la interpretacion IA antes de
    llegar aqui. Esta funcion solo conserva terminos utiles para reforzar la
    busqueda y puntuar coincidencia lexica.
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
    perfiles = normalizar_texto(metadata.get("perfiles", ""))
    grupos = normalizar_texto(metadata.get("grupos", ""))
    tipos_periodo = normalizar_texto(metadata.get("tipos_periodo", ""))

    coincidencias_contenido = sum(1 for token in tokens if token in contenido)
    coincidencias_titulo = sum(1 for token in tokens if token in titulo)
    coincidencias_tipo = sum(1 for token in tokens if token in tipo_documento)
    coincidencias_perfiles = sum(1 for token in tokens if token in perfiles)
    coincidencias_grupos = sum(1 for token in tokens if token in grupos)
    coincidencias_periodo = sum(1 for token in tokens if token in tipos_periodo)

    return (
        coincidencias_contenido
        + (coincidencias_titulo * 3)
        + (coincidencias_tipo * 2)
        + (coincidencias_perfiles * 2)
        + coincidencias_grupos
        + coincidencias_periodo
    ) / max(len(tokens), 1)


def calcular_score_ranking(distancia, coincidencia_lexica):
    """
    Combina distancia semantica y coincidencia lexica en un unico score
    (menor es mejor). La distancia manda; la coincidencia lexica solo puede
    corregirla hasta un tope (PESO_LEXICO * LEXICA_MAXIMA_CONSIDERADA), para
    que una coincidencia lexica incidental (p. ej. una palabra generica que
    matchea el titulo de otro documento) no le gane a una ventaja semantica
    clara. Ver pending_ranking_lexico_no_escala en memoria para el contexto
    del incidente que motivo este cambio.
    """
    distancia = distancia if distancia is not None else 999999
    ajuste = min(coincidencia_lexica, LEXICA_MAXIMA_CONSIDERADA) * PESO_LEXICO
    return distancia - ajuste


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
    uuid_version = str(metadata_base.get("uuid_version") or "").strip()
    id_version = str(metadata_base.get("id_version") or "").strip()
    version_fragmento = uuid_version or id_version

    for indice, fragmento in enumerate(fragmentos, start=1):
        if version_fragmento:
            id_fragmento = f"doc_{id_documento}_ver_{version_fragmento}_frag_{indice}"
        else:
            id_fragmento = f"doc_{id_documento}_frag_{indice}"
        if isinstance(fragmento, dict):
            contenido = str(fragmento.get("contenido") or "")
            pagina_inicio = fragmento.get("pagina_inicio")
            pagina_fin = fragmento.get("pagina_fin")
        else:
            contenido = str(fragmento)
            pagina_inicio = None
            pagina_fin = None

        # Los metadatos permiten filtrar despues por perfil, carrera, vigencia,
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


def actualizar_metadata_version_chroma(uuid_version, metadata_actualizada):
    collection = obtener_coleccion()
    resultados = collection.get(
        where={"uuid_version": str(uuid_version)},
        include=["metadatas"],
    )

    ids = resultados.get("ids", [])
    metadatas = resultados.get("metadatas", [])
    if not ids:
        return 0

    metadatas_actualizadas = []
    for indice, _ in enumerate(ids):
        metadata = {}
        if indice < len(metadatas) and isinstance(metadatas[indice], dict):
            metadata = metadatas[indice].copy()
        metadata.update(metadata_actualizada)
        metadatas_actualizadas.append(metadata)

    collection.update(
        ids=ids,
        metadatas=metadatas_actualizadas,
    )

    return len(ids)


def eliminar_fragmento_chroma(id_fragmento):
    collection = obtener_coleccion()
    collection.delete(ids=[id_fragmento])


def eliminar_documento_chroma(id_documento):
    collection = obtener_coleccion()
    collection.delete(where={"id_documento": str(id_documento)})


def eliminar_version_chroma(uuid_version):
    collection = obtener_coleccion()
    collection.delete(where={"uuid_version": str(uuid_version)})


def separar_filtros_chroma(filtros):
    filtros_exactos = {}
    filtros_flexibles = {}

    for clave, valor in (filtros or {}).items():
        if valor in [None, ""]:
            continue
        if clave in FILTROS_LISTA_METADATA:
            filtros_flexibles[clave] = valor
        else:
            filtros_exactos[clave] = valor

    return filtros_exactos, filtros_flexibles


def valores_metadata_lista(valor):
    if isinstance(valor, list):
        return valor

    if isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            return []
        try:
            data = json.loads(texto)
        except json.JSONDecodeError:
            return [texto]
        if isinstance(data, list):
            return data
        return [data]

    if valor in [None, ""]:
        return []

    return [valor]


def metadata_coincide_filtro_lista(metadata, clave, valor_filtro):
    valor_normalizado = normalizar_texto(valor_filtro)
    if not valor_normalizado:
        return True

    valores = valores_metadata_lista((metadata or {}).get(clave))
    return any(normalizar_texto(valor) == valor_normalizado for valor in valores)


def metadata_permite_perfil(metadata, valor_filtro_perfil):
    """
    Control de acceso duro por perfil (estudiante/docente/aspirante/externo).
    A diferencia de grupos/tipos_periodo, la ausencia de un perfil declarado
    NO abre un documento restringido: solo son visibles los documentos sin
    metadata de perfiles o marcados explicitamente como publicos. Por eso
    esta funcion se evalua siempre, no solo cuando hay un filtro activo.
    """
    valores_documento = [
        normalizar_texto(valor)
        for valor in valores_metadata_lista((metadata or {}).get("perfiles"))
    ]

    if not valores_documento or any(valor in PERFILES_ACCESO_PUBLICO for valor in valores_documento):
        return True

    valor_normalizado = normalizar_texto(valor_filtro_perfil)
    if not valor_normalizado:
        return False

    return valor_normalizado in valores_documento


def metadata_cumple_filtros_flexibles(metadata, filtros):
    filtros = filtros or {}

    if not metadata_permite_perfil(metadata, filtros.get("perfiles", "")):
        return False

    return all(
        metadata_coincide_filtro_lista(metadata, clave, valor)
        for clave, valor in filtros.items()
        if clave != "perfiles"
    )


def construir_where_chroma(filtros):
    """
    Convierte filtros simples de Django a formato válido para ChromaDB.
    Si hay un filtro:
        {"ambito": "PUBLICO"}
    Si hay varios:
        {"$and": [{"ambito": "PUBLICO"}, {"perfil": "ESTUDIANTE"}]}
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

    filtros_exactos, filtros_flexibles = separar_filtros_chroma(filtros)
    where = construir_where_chroma(filtros_exactos)

    # Chroma devuelve documentos, metadatos y distancia de similitud.
    # SAVI usa estos fragmentos como contexto para la respuesta de Qwen.
    total_candidatos = max(total_resultados, 8)
    if filtros_flexibles:
        total_candidatos = max(total_resultados * 10, 30)

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
        if not metadata_cumple_filtros_flexibles(metadata, filtros_flexibles):
            continue
        fragmentos.append({
            "contenido": texto,
            "metadata": metadata,
            "distancia": distancia,
            "coincidencia_lexica": puntuar_coincidencia_lexica(pregunta, texto, metadata),
        })

    for fragmento in fragmentos:
        fragmento["score_ranking"] = calcular_score_ranking(
            fragmento["distancia"], fragmento["coincidencia_lexica"]
        )

    fragmentos.sort(key=lambda item: item["score_ranking"])

    resultado = fragmentos[:total_resultados]

    if logger.isEnabledFor(logging.INFO):
        top_3 = resultado[:3]
        resumen = "; ".join(
            "#{pos} doc_id={doc_id} titulo={titulo!r} distancia={distancia} "
            "coincidencia_lexica={lexica} score={score}".format(
                pos=indice + 1,
                doc_id=item["metadata"].get("id_documento", "desconocido"),
                titulo=item["metadata"].get("titulo", "sin titulo"),
                distancia=item["distancia"],
                lexica=item["coincidencia_lexica"],
                score=item["score_ranking"],
            )
            for indice, item in enumerate(top_3)
        )
        logger.info("Ranking de fragmentos para pregunta=%r -> %s", pregunta, resumen)

    return resultado
