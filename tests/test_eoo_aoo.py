"""EOO, AOO y umbrales del criterio B de analisis/eoo_aoo.py."""
import numpy as np
import pandas as pd
import pytest

from analisis.eoo_aoo import (
    MIN_LOCALIDADES,
    UMBRALES_AOO,
    UMBRALES_EOO,
    celdas_aoo,
    eoo_km2,
    metricas,
    umbral,
)


def test_eoo_de_un_cuadrado():
    # cuadrado de 10 x 10 km con un punto interior
    x = np.array([0, 10_000, 10_000, 0, 5_000])
    y = np.array([0, 0, 10_000, 10_000, 5_000])
    assert eoo_km2(x, y) == pytest.approx(100)


def test_eoo_con_menos_de_tres_puntos_o_colineales_es_cero():
    assert eoo_km2(np.array([0, 1_000]), np.array([0, 0])) == 0
    assert eoo_km2(np.array([0, 1_000, 2_000]), np.array([0, 1_000, 2_000])) == 0


def test_celdas_aoo_de_2_km():
    x = np.array([100, 1_900, 2_100, -100])
    y = np.array([100, 1_900, 100, 100])
    assert celdas_aoo(x, y) == {(0, 0), (1, 0), (-1, 0)}


@pytest.mark.parametrize("valor, umbrales, esperado", [
    (50, UMBRALES_EOO, "CR"), (100, UMBRALES_EOO, "EN"), (4_999, UMBRALES_EOO, "EN"),
    (19_999, UMBRALES_EOO, "VU"), (20_000, UMBRALES_EOO, "No alcanza"),
    (8, UMBRALES_AOO, "CR"), (1_999, UMBRALES_AOO, "VU"),
])
def test_umbral_criterio_b(valor, umbrales, esperado):
    assert umbral(valor, umbrales, localidades=MIN_LOCALIDADES) == esperado


def test_umbral_con_pocas_localidades():
    assert umbral(1, UMBRALES_EOO, localidades=MIN_LOCALIDADES - 1) == "Pocos registros"


def test_metricas_eoo_nunca_menor_que_aoo():
    # 12 localidades en una linea de 22 km: EOO = 0 (colineales), AOO = 12 celdas
    sub = pd.DataFrame({"x": np.arange(12) * 2_000.0 + 1, "y": np.full(12, 1.0),
                        "incertidumbre_m": np.full(12, 100.0)})
    m = metricas(sub)
    assert m["localidades"] == 12
    assert m["aoo_km2"] == 48
    assert m["eoo_km2"] == 48
    assert m["umbral_b1"] == "CR" and m["umbral_b2"] == "EN"


def test_metricas_aoo_excluye_puntos_imprecisos():
    sub = pd.DataFrame({"x": [1.0, 5_001.0], "y": [1.0, 1.0],
                        "incertidumbre_m": [100.0, 5_000.0]})
    assert metricas(sub)["celdas_aoo"] == 1
