"""Etapa 04: guardado del dataset procesado y lectura para los analisis."""
import shutil

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from config import DIR_PROCESADO

# Columnas de texto repetitivas que se guardan como categoria (menos RAM al leer)
MAX_CARDINALIDAD_CATEGORIA = 5_000


def guardar(df: pd.DataFrame, destino=DIR_PROCESADO) -> None:
    """Escribe un Parquet particionado por `unidad` (zona UTM o pais)."""
    df = df.copy()
    for col in df.select_dtypes(include=["object", "string"]).columns:
        if col != "unidad" and df[col].nunique() <= MAX_CARDINALIDAD_CATEGORIA:
            df[col] = df[col].astype("category")

    if destino.exists():
        shutil.rmtree(destino)
    tabla = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_to_dataset(tabla, root_path=destino, partition_cols=["unidad"])


def cargar_procesado(unidades=None, columnas=None, destino=DIR_PROCESADO) -> pd.DataFrame:
    """Lee el dataset procesado. `unidades` filtra particiones sin leer las demas.

    Ejemplos:
        cargar_procesado(["14a"])                           # una zona UTM
        cargar_procesado(["11", "12", "13", "14a", "14b", "15", "16"])
        cargar_procesado(["GUATEMALA", "BELICE"], columnas=["especie", "unidad"])
    """
    dataset = ds.dataset(destino, format="parquet", partitioning="hive")
    filtro = ds.field("unidad").isin(list(unidades)) if unidades is not None else None
    df = dataset.to_table(columns=columnas, filter=filtro).to_pandas()
    if "unidad" in df.columns:
        df["unidad"] = df["unidad"].astype(str)
    return df
