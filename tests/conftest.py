"""Registros sinteticos con la forma del maestro del SNIB (columnas de config.COLUMNAS).

Las pruebas no usan el Parquet real: cada caso de la depuracion se reproduce con
unas pocas filas construidas a mano.
"""
import pandas as pd
import pytest

from config import COLUMNAS, NULO_SNIB

# Valores de un registro "tipico": Mexico, zona 14a, especie terrestre sin categoria
BASE = {c: NULO_SNIB for c in COLUMNAS} | {
    "ordenvalido": "Rodentia",
    "familiavalida": "Cricetidae",
    "generovalido": "Peromyscus",
    "especievalida": "Peromyscus maniculatus",
    "taxonvalidado": "SI",
    "longitud": -100.5,
    "latitud": 19.5,
    "altitudmapa": "2300",
    "incertidumbreXY": "500",
    "paismapa": "MEXICO",
    "ambiente": "Terrestre",
    "aniocolecta": "1985",
    "mescolecta": "6",
    "diacolecta": "15",
    "procedenciaejemplar": "PreservedSpecimen",
}


def registros(*cambios: dict) -> pd.DataFrame:
    """Un registro por diccionario; cada uno sobrescribe campos de BASE."""
    filas = [BASE | {"idejemplar": f"id{i}"} | c for i, c in enumerate(cambios)]
    return pd.DataFrame(filas, columns=COLUMNAS)


@pytest.fixture
def crear_registros():
    return registros
