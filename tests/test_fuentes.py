"""Tabla de atribucion de pipeline/fuentes.py."""
import pandas as pd

from pipeline.fuentes import normalizar_licencia, tabla_fuentes, tabla_licencias


def test_normalizar_licencia_unifica_variantes():
    s = pd.Series(["CC_BY_4_0", "CC-BY", "CC_BY_NC_4_0", "CC-BY-NC", "CC0", "OTRA", None])
    assert normalizar_licencia(s).tolist() == [
        "CC BY 4.0", "CC BY 4.0", "CC BY-NC 4.0", "CC BY-NC 4.0", "CC0 1.0", "OTRA",
        "sin licencia"]


def test_tablas_de_fuentes_y_licencias():
    df = pd.DataFrame({
        "formadecitar": ["Museo A. https://doi.org/10.1/abc.", "Museo A. https://doi.org/10.1/abc.",
                         "Naturalista", "Naturalista"],
        "licencia": ["CC BY 4.0", "CC BY 4.0", "CC BY-NC 4.0", "CC0 1.0"],
        "en_mexico": [True, False, True, True],
    })
    f = tabla_fuentes(df)
    assert f["registros"].tolist() == [2, 1, 1]
    assert f.loc[0, "doi"] == "https://doi.org/10.1/abc"
    assert f.loc[0, "registros_mexico"] == 1
    lic = tabla_licencias(df)
    assert lic.index.tolist() == ["CC0 1.0", "CC BY 4.0", "CC BY-NC 4.0"]
    assert lic["registros_mexico"].sum() == 3
