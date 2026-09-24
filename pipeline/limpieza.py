"""Etapa 02: nulos, tipos, taxonomia a nivel especie y codigos de riesgo."""
import numpy as np
import pandas as pd

from config import ANIO_VALIDO, ESPECIES_INTRODUCIDAS, NULO_SNIB

CATEGORIAS_NOM = ["Pr", "A", "P", "E"]                      # menor -> mayor riesgo
CATEGORIAS_IUCN = ["DD", "LC", "NT", "VU", "EN", "CR", "EW", "EX"]
CATEGORIAS_CITES = ["III", "II", "I"]
ORDENES_MARINOS = ["Cetacea", "Sirenia"]
FAMILIAS_MARINAS = ["Otariidae", "Phocidae", "Odobenidae"]


def _a_numero(serie, minimo=None, maximo=None):
    x = pd.to_numeric(serie, errors="coerce")
    if minimo is not None:
        x = x.where(x >= minimo)
    if maximo is not None:
        x = x.where(x <= maximo)
    return x


def _codigo(serie, patron, categorias):
    """Extrae el codigo de una categoria anotada, p. ej.
    'Amenazada (A) (Publicado en NOM-059 ... como X)' -> 'A'."""
    cod = serie.str.extract(patron, expand=False)
    return pd.Categorical(cod, categories=categorias, ordered=True)


def valor_nivel_especie(df: pd.DataFrame, col: str) -> pd.Series:
    """Valor de `col` para la especie completa (indice: especie).

    Varios campos del SNIB (endemismo, NOM-059, IUCN) se asignan por taxon, y
    una subespecie puede ser endemica o estar listada sin que la especie lo este
    (p. ej. Nasua narica nelsoni, de Cozumel). Se toma el valor mas frecuente
    entre los registros sin subespecie; si la especie solo tiene registros con
    subespecie, el valor cuando todas coinciden y NaN si no.
    """
    con_especie = df[df["especie"].notna()]
    sin_sub = con_especie[con_especie["subespecie"].isna()]
    nivel = sin_sub.groupby("especie")[col].agg(
        lambda s: s.astype(object).value_counts(dropna=False).idxmax())
    solo_sub = con_especie[~con_especie["especie"].isin(nivel.index)]
    uniforme = solo_sub.groupby("especie")[col].agg(
        lambda s: s.iat[0] if s.astype(object).nunique(dropna=False) == 1 else np.nan)
    return pd.concat([nivel, uniforme])


def _parsear_anp(anp: pd.Series) -> pd.DataFrame:
    """Columnas dentro_anp, anp_tipo y anp_nombre (del ANP que contiene el punto)
    y anp_distancia_km (al ANP mas cercano cuando el punto esta fuera)."""
    entradas = (anp.dropna().str.split(r"\s*\|\s*").explode()
                .str.extract(r"^(?P<tipo>[^»]+)»\s*(?P<nombre>.*?)\s*"
                             r"(?:\{a (?P<km>[\d.]+) km\})?$"))
    entradas["km"] = pd.to_numeric(entradas["km"])
    dentro = entradas[entradas["km"].isna()]
    primera = dentro.groupby(level=0).first()
    resultado = pd.DataFrame(index=anp.index)
    resultado["dentro_anp"] = anp.index.isin(dentro.index)
    resultado["anp_tipo"] = primera["tipo"].str.strip()
    resultado["anp_nombre"] = primera["nombre"]
    resultado["anp_distancia_km"] = entradas.groupby(level=0)["km"].min()
    resultado.loc[resultado["dentro_anp"], "anp_distancia_km"] = 0.0
    return resultado


def limpieza(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 1. Nulos del SNIB ("\N") y cadenas vacias -> NaN
    texto = df.select_dtypes(include=["object", "string"]).columns
    df[texto] = df[texto].replace({NULO_SNIB: np.nan, "": np.nan})

    # 2. Tipos numericos
    df["altitud_m"] = _a_numero(df.pop("altitudmapa"), -500, 6000)
    df["incertidumbre_m"] = _a_numero(df.pop("incertidumbreXY"), 0)
    df["anio"] = _a_numero(df.pop("aniocolecta"), *ANIO_VALIDO).astype("Int16")
    df["mes"] = _a_numero(df.pop("mescolecta"), 1, 12).astype("Int8")
    df["dia"] = _a_numero(df.pop("diacolecta"), 1, 31).astype("Int8")

    # 3. Taxonomia: especievalida mezcla binomios y trinomios (subespecies)
    #    y algunos traen subgenero: "Artibeus (Dermanura) glaucus" -> "Artibeus glaucus"
    partes = df["especievalida"].str.replace(r"\s*\([^)]*\)", "", regex=True).str.split()
    df["especie"] = partes.str[:2].str.join(" ")
    df["subespecie"] = partes.str[2]
    df["nivel_taxonomico"] = np.select(
        [df["especie"].notna(), df["generovalido"].notna(), df["familiavalida"].notna()],
        ["especie", "genero", "familia"],
        default="orden o superior",
    )

    # 4. Codigos de riesgo (los textos traen anotaciones largas)
    df["nom059_cod"] = _codigo(df["nom059"], r"\((Pr|P|A|E)\)", CATEGORIAS_NOM)
    df["iucn_cod"] = _codigo(df["iucn"], r"\((LC|NT|VU|EN|CR|DD|EW|EX)\)", CATEGORIAS_IUCN)
    df["cites_cod"] = _codigo(df["cites"], r"^Ap\w+ndice (III|II|I)\b", CATEGORIAS_CITES)
    df["en_nom059"] = df["nom059_cod"].notna()
    df["iucn_amenazada"] = df["iucn_cod"].isin(["VU", "EN", "CR", "EW"])
    df["endemica"] = df.pop("endemismo").notna()          # del taxon del registro
    # el SNIB solo llena `endemismo` en registros de Mexico
    endemicas = valor_nivel_especie(df[df["paismapa"] == "MEXICO"], "endemica")
    df["endemica_especie"] = df["especie"].map(endemicas).fillna(False).astype(bool)
    df["prioritaria"] = df["prioritaria"].notna()
    df["taxonvalidado"] = df["taxonvalidado"].eq("SI")

    # 5. Ambiente: separar marinos (cetaceos, sirenios, pinnipedos). ~10% de los
    #    registros no traen `ambiente`, asi que tambien se usa la taxonomia.
    amb = df["ambiente"].fillna("")
    df["es_marino"] = (
        (amb.str.contains("Marino") & ~amb.str.contains("Terrestre"))
        | df["ordenvalido"].isin(ORDENES_MARINOS)
        | df["familiavalida"].isin(FAMILIAS_MARINAS)
    )

    # 6. Exoticas: a nivel especie (la marca del SNIB es por registro e incompleta)
    exoticas = set(df.loc[df["exoticainvasora"].notna(), "especie"].dropna())
    df["es_exotica"] = df["especie"].isin(exoticas | set(ESPECIES_INTRODUCIDAS))

    # 7. ANP. `anp` lista una o varias areas separadas por " | ", p. ej.
    #    "Federal» Janos" (dentro) o "Estatal» Quebrada de Santa Barbara {a 4.111 km}"
    #    (FUERA, a esa distancia). Dentro = alguna entrada sin distancia.
    df = df.join(_parsear_anp(df["anp"]))

    # 8. Duplicados de evento: mismo taxon, mismo punto y misma fecha. Son
    #    ejemplares distintos (se conservan) pero redundantes para analisis de
    #    presencia; se marcan para poder excluirlos con ~dup_evento.
    taxon = df["especievalida"].fillna(df["generovalido"]).fillna(df["familiavalida"])
    clave = pd.DataFrame({
        "taxon": taxon,
        "lon": df["longitud"].round(4),
        "lat": df["latitud"].round(4),
        "anio": df["anio"], "mes": df["mes"], "dia": df["dia"],
    })
    df["dup_evento"] = clave.duplicated(keep="first")

    return df
