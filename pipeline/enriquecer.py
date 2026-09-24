"""Etapa 03: zona UTM, unidad de comparacion, celda de grid y clases derivadas."""
import numpy as np
import pandas as pd

from config import CELDA_GRADOS, INCERTIDUMBRE_CORTES_M, LAT_MEXICO, TIPO_REGISTRO, ZONAS_UTM


def asignar_zona(lon, lat, pais) -> pd.Series:
    """Zona UTM de Mexico con el criterio (lon_oeste, lon_este]; NaN fuera de Mexico."""
    nombres = list(ZONAS_UTM)
    limites = [ZONAS_UTM[nombres[0]][0]] + [ZONAS_UTM[z][1] for z in nombres]
    for a, b in zip(nombres, nombres[1:]):
        if ZONAS_UTM[a][1] != ZONAS_UTM[b][0]:
            raise ValueError(f"Zonas {a} y {b} no son contiguas en config.ZONAS_UTM")

    zona = pd.cut(lon, bins=limites, labels=nombres, right=True)
    en_mexico = (pais == "MEXICO") & lat.between(*LAT_MEXICO)
    return zona.where(en_mexico)


def enriquecer(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Zona UTM (Mexico) y unidad de comparacion (zona para Mexico, pais fuera)
    df["zona_utm"] = asignar_zona(df["longitud"], df["latitud"], df["paismapa"])
    df["unidad"] = df["zona_utm"].astype("string").fillna(df["paismapa"])

    # Celda regular en grados: id estable + centroide para mapear
    ix = np.floor(df["longitud"] / CELDA_GRADOS).astype(int)
    iy = np.floor(df["latitud"] / CELDA_GRADOS).astype(int)
    df["celda_id"] = ix.astype(str) + "_" + iy.astype(str)
    df["celda_lon"] = (ix + 0.5) * CELDA_GRADOS
    df["celda_lat"] = (iy + 0.5) * CELDA_GRADOS

    # Tiempo
    df["decada"] = (df["anio"] // 10 * 10).astype("Int16")

    # Precision espacial
    c1, c2 = INCERTIDUMBRE_CORTES_M
    df["clase_incertidumbre"] = pd.cut(
        df["incertidumbre_m"], bins=[-np.inf, c1, c2, np.inf],
        labels=[f"<{c1 // 1000} km", f"{c1 // 1000}-{c2 // 1000} km", f">{c2 // 1000} km"],
    ).cat.add_categories("desconocida").fillna("desconocida")

    # Origen del registro agrupado (coleccion vs ciencia ciudadana vs fototrampeo)
    df["tipo_registro"] = df["procedenciaejemplar"].map(TIPO_REGISTRO).fillna("Otro/desconocido")

    return df
