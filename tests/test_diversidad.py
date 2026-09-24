"""Riqueza (rarefaccion, Chao1, cobertura) y diversidad beta de analisis/comparativo.py."""
from math import comb

import numpy as np
import pandas as pd
import pytest

from analisis.comparativo import beta_pares, chao1, cobertura, riqueza_rarefactada


def _rarefaccion_directa(conteos, n):
    N = sum(conteos)
    return sum(1 - comb(N - c, n) / comb(N, n) for c in conteos)


@pytest.mark.parametrize("n", [1, 2, 5, 9])
def test_rarefaccion_coincide_con_formula_de_hurlbert(n):
    conteos = [5, 3, 1, 1]
    esperado = _rarefaccion_directa(conteos, n)
    assert riqueza_rarefactada(np.array(conteos), n) == pytest.approx(esperado)


def test_rarefaccion_extremos():
    conteos = np.array([5, 3, 1, 1])
    assert riqueza_rarefactada(conteos, 1) == pytest.approx(1.0)
    assert riqueza_rarefactada(conteos, 10) == 4.0
    assert riqueza_rarefactada(conteos, 50) == 4.0


def test_rarefaccion_con_muestras_grandes_no_desborda():
    conteos = np.array([50_000, 20_000, 5, 1])
    assert 1 < riqueza_rarefactada(conteos, 1_000) < 4


def test_chao1_sin_singletons_es_la_riqueza_observada():
    assert chao1([4, 3, 2, 2]) == 4


def test_chao1_con_correccion_de_sesgo():
    # S_obs + (n-1)/n * f1(f1-1) / (2(f2+1)), n=10, f1=3, f2=1
    assert chao1([5, 2, 1, 1, 1]) == pytest.approx(5 + 9 / 10 * 3 * 2 / 4)


def test_cobertura():
    assert cobertura([4, 3, 2, 2]) == 1.0
    n, f1, f2 = 10, 3, 1
    esperado = 1 - f1 / n * ((n - 1) * f1 / ((n - 1) * f1 + 2 * f2))
    assert cobertura([5, 2, 1, 1, 1]) == pytest.approx(esperado)


def test_beta_recambio_y_anidamiento():
    pa = pd.DataFrame(
        [[1, 1, 1, 1, 0, 0],    # A
         [1, 1, 0, 0, 0, 0],    # B: subconjunto de A (anidamiento puro)
         [0, 0, 0, 0, 1, 1]],   # C: nada en comun con A (recambio puro)
        index=["A", "B", "C"], columns=list("abcdef")).astype(bool)
    t = beta_pares(pa).set_index(["unidad_1", "unidad_2"])

    ab = t.loc[("A", "B")]
    assert (ab["compartidas"], ab["solo_1"], ab["solo_2"]) == (2, 2, 0)
    assert ab["jaccard_similitud"] == 0.5
    assert ab["beta_recambio"] == 0
    assert ab["beta_anidamiento"] == ab["beta_sorensen"] == pytest.approx(2 / 6, abs=1e-3)

    ac = t.loc[("A", "C")]
    assert ac["jaccard_similitud"] == 0
    assert ac["beta_sorensen"] == ac["beta_recambio"] == 1
    assert ac["beta_anidamiento"] == 0
