"""Etapa 01: lectura del Parquet maestro con proyeccion de columnas y filtros."""
import pandas as pd
import pyarrow.dataset as ds

from config import COLUMNAS, PARQUET_MAESTRO


def ingesta(columnas=COLUMNAS, paises=None, excluir_fosiles=True) -> pd.DataFrame:
    """Lee solo `columnas` y aplica los filtros al leer (no en memoria).

    paises: lista de valores de `paismapa` (p. ej. ["MEXICO"]); None = todos.
    """
    dataset = ds.dataset(PARQUET_MAESTRO, format="parquet")

    filtro = None
    if excluir_fosiles:
        filtro = ds.field("procedenciaejemplar") != "FossilSpecimen"
        # != descarta nulos en pyarrow; se conservan explicitamente
        filtro = filtro | ds.field("procedenciaejemplar").is_null()
    if paises is not None:
        f_pais = ds.field("paismapa").isin(list(paises))
        filtro = f_pais if filtro is None else filtro & f_pais

    return dataset.to_table(columns=list(columnas), filter=filtro).to_pandas()
