"""Clasificacion INEGI (uso_suelo), estacionalidad (temporal) y etiquetas (estilo)."""
import pandas as pd
import pytest

from analisis.estilo import cursiva
from analisis.temporal import estacionalidad
from analisis.uso_suelo import clasificar_clase


@pytest.mark.parametrize("clase, esperado", [
    ("ZONA URBANA", ("Urbana", None)),
    ("AGRICULTURA DE TEMPORAL ANUAL", ("Agrícola", None)),
    ("PASTIZAL INDUCIDO", ("Pastizal o bosque inducido", None)),
    ("CUERPO DE AGUA", ("Agua o sin vegetación", None)),
    ("NO EMPATA", (None, None)),
    (None, (None, None)),
])
def test_clases_inegi_sin_formacion(clase, esperado):
    assert clasificar_clase(clase) == esperado


def test_vegetacion_secundaria_conserva_su_formacion():
    primaria = clasificar_clase("BOSQUE DE PINO-ENCINO")
    secundaria = clasificar_clase("VEGETACIÓN SECUNDARIA ARBÓREA DE BOSQUE DE PINO-ENCINO")
    assert primaria[0] == "Primaria" and secundaria[0] == "Secundaria"
    assert primaria[1] is not None
    assert secundaria[1] == primaria[1]


def test_estacionalidad_corrige_por_esfuerzo():
    # 'A b' siempre representa la mitad de los murcielagos del mes -> indice 1 todo el ano,
    # aunque el esfuerzo (registros por mes) sea muy desigual
    filas = []
    for mes in range(1, 13):
        n = 10 if mes in (4, 5) else 2
        filas += [{"especie": "A b", "mes": mes}] * n + [{"especie": "C d", "mes": mes}] * n
    df = pd.DataFrame(filas).assign(ordenvalido="Chiroptera", latitud=28.0)
    est = estacionalidad(df, ["A b"])
    assert est["banda"].unique().tolist() == ["Norte (≥ 24°)"]
    assert est["indice"].tolist() == [1.0] * 12
    assert est["registros_banda"].iat[0] == 40


def test_cursiva_en_mathtext():
    assert cursiva("Romerolagus diazi") == r"$\mathit{Romerolagus\ diazi}$"
