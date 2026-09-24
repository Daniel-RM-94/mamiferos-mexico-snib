"""Zona UTM, celda, decada y clases de pipeline/enriquecer.py."""
import pandas as pd
import pytest

from pipeline import enriquecer as mod
from pipeline.enriquecer import asignar_zona, enriquecer
from pipeline.limpieza import limpieza


def _zona(lon, lat=19.5, pais="MEXICO"):
    return asignar_zona(pd.Series([lon]), pd.Series([lat]), pd.Series([pais])).iat[0]


@pytest.mark.parametrize("lon, zona", [
    (-115.0, "11"), (-110.0, "12"), (-105.0, "13"),
    (-100.5, "14a"), (-97.0, "14b"), (-93.0, "15"), (-87.0, "16"),
])
def test_zona_por_longitud(lon, zona):
    assert _zona(lon) == zona


def test_limite_entre_zonas_es_abierto_al_oeste():
    # criterio de CONABIO para 14a: lon > -102 & lon <= -99
    assert _zona(-102.0) == "13"
    assert _zona(-99.0) == "14a"
    assert _zona(-101.9999) == "14a"


def test_sin_zona_fuera_de_mexico_o_de_latitud():
    assert pd.isna(_zona(-90.5, pais="GUATEMALA"))
    assert pd.isna(_zona(-100.5, lat=34.0))


def test_zonas_no_contiguas_fallan(monkeypatch):
    monkeypatch.setattr(mod, "ZONAS_UTM", {"a": (-110, -105), "b": (-104, -100)})
    with pytest.raises(ValueError, match="no son contiguas"):
        _zona(-106.0)


def test_enriquecer_unidad_celda_y_clases(crear_registros):
    df = enriquecer(limpieza(crear_registros(
        {"longitud": -100.6, "latitud": 19.4, "incertidumbreXY": "500"},
        {"longitud": -90.5, "latitud": 15.0, "paismapa": "GUATEMALA",
         "incertidumbreXY": "\\N", "procedenciaejemplar": "HumanObservation"},
    )))
    assert df["unidad"].tolist() == ["14a", "GUATEMALA"]
    # celda de 0.25 grados: -100.6 -> [-100.75, -100.5), 19.4 -> [19.25, 19.5)
    assert df.at[0, "celda_id"] == "-403_77"
    assert (df.at[0, "celda_lon"], df.at[0, "celda_lat"]) == (-100.625, 19.375)
    assert df.at[0, "decada"] == 1980
    assert df["clase_incertidumbre"].astype(str).tolist() == ["<1 km", "desconocida"]
    assert df["tipo_registro"].tolist() == ["Coleccion", "Observacion humana"]
