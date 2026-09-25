"""Cuencas oceanicas y fecha central de la temporada de analisis/marinos.py."""
import numpy as np
import pytest

from analisis.marinos import asignar_cuenca, fecha_central


@pytest.mark.parametrize("lugar, lat, lon, cuenca", [
    ("Bahía de La Paz", 24.3, -110.4, "Golfo de California"),
    ("Guaymas", 27.9, -110.9, "Golfo de California"),
    ("San Felipe", 31.0, -114.8, "Golfo de California"),
    ("Laguna Ojo de Liebre", 27.8, -114.2, "Pacífico"),
    ("Bahía Magdalena", 24.6, -112.0, "Pacífico"),
    ("Mazatlán (al sur de Punta Piaxtla)", 23.2, -106.45, "Pacífico"),
    ("Bahía de Banderas", 20.6, -105.3, "Pacífico"),
    ("Salina Cruz", 16.1, -95.2, "Pacífico"),
    ("Veracruz", 19.2, -96.1, "Golfo de México"),
    ("Holbox", 21.55, -87.3, "Golfo de México"),
    ("Cancún", 21.1, -86.8, "Caribe"),
    ("Bahía de Chetumal", 18.5, -88.3, "Caribe"),
])
def test_asignar_cuenca(lugar, lat, lon, cuenca):
    assert asignar_cuenca([lon], [lat])[0] == cuenca, lugar


def test_fecha_central_de_un_solo_mes():
    n = np.zeros(12)
    n[1] = 50                                   # febrero
    assert fecha_central(n, np.full(12, 100)) == pytest.approx(2.5)


def test_fecha_central_cruza_el_fin_de_anio():
    n = np.zeros(12)
    n[[11, 0]] = 30                             # diciembre y enero
    centro = fecha_central(n, np.full(12, 100))
    assert min(abs(centro - 1), abs(centro - 13)) < 1e-9     # 1 de enero


def test_fecha_central_corrige_por_esfuerzo():
    # la especie aparece en proporcion al esfuerzo salvo en marzo; febrero tiene 10 veces
    # mas esfuerzo, lo que en conteos crudos arrastraria la fecha hacia febrero
    esfuerzo = np.full(12, 100.0)
    esfuerzo[1] = 1000
    especie = esfuerzo * 0.1
    especie[2] = 50
    assert fecha_central(especie, esfuerzo) == pytest.approx(3.5)
