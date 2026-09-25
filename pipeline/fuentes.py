"""Tabla de atribucion: fuentes originales de los registros, con su licencia.

El SNIB integra datos de cientos de proyectos y colecciones, y cada conjunto
conserva la licencia de quien lo aporto (campos `licenciauso` y `formadecitar`).
Este script resume, para los registros usados en el analisis (sin fosiles),
cada forma de citar con su licencia y numero de registros, y escribe:

    docs/fuentes_datos.csv       una fila por fuente (cita + licencia)
    docs/licencias_datos.csv     registros por licencia, en total y en Mexico

Uso:
    .\\venv\\Scripts\\python.exe -m pipeline.fuentes
"""
import pandas as pd
import pyarrow.dataset as ds

from config import PARQUET_MAESTRO, RAIZ

DESTINO = RAIZ / "docs"
# El SNIB escribe la misma licencia de dos formas (p. ej. CC_BY_4_0 y CC-BY)
LICENCIAS = {
    "CC0_1_0": "CC0 1.0", "CC0": "CC0 1.0",
    "CC_BY_4_0": "CC BY 4.0", "CC-BY": "CC BY 4.0",
    "CC-BY-SA": "CC BY-SA 4.0",
    "CC-BY-ND": "CC BY-ND 4.0",
    "CC_BY_NC_4_0": "CC BY-NC 4.0", "CC-BY-NC": "CC BY-NC 4.0",
    "CC-BY-NC-SA": "CC BY-NC-SA 4.0",
    "CC-BY-NC-ND": "CC BY-NC-ND 4.0",
}
ORDEN = ["CC0 1.0", "CC BY 4.0", "CC BY-SA 4.0", "CC BY-ND 4.0", "CC BY-NC 4.0",
         "CC BY-NC-SA 4.0", "CC BY-NC-ND 4.0"]


def normalizar_licencia(serie: pd.Series) -> pd.Series:
    """Codigo del SNIB -> nombre de la licencia; los desconocidos se conservan tal cual."""
    return serie.map(LICENCIAS).fillna(serie.fillna("sin licencia"))


def leer() -> pd.DataFrame:
    tabla = ds.dataset(PARQUET_MAESTRO).to_table(
        columns=["licenciauso", "formadecitar", "paismapa", "procedenciaejemplar"])
    df = tabla.to_pandas()
    df = df[df["procedenciaejemplar"].fillna("") != "FossilSpecimen"]
    df["licencia"] = normalizar_licencia(df["licenciauso"])
    df["en_mexico"] = df["paismapa"] == "MEXICO"
    return df


def tabla_fuentes(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["formadecitar", "licencia"], dropna=False)
    t = pd.DataFrame({"registros": g.size(), "registros_mexico": g["en_mexico"].sum()})
    t = t.reset_index().rename(columns={"formadecitar": "forma_de_citar"})
    t["doi"] = t["forma_de_citar"].str.extract(r"(https?://doi\.org/[^\s,;)]+)", expand=False)
    t["doi"] = t["doi"].str.rstrip(".")
    return t.sort_values(["registros", "forma_de_citar"], ascending=[False, True],
                         ignore_index=True)


def tabla_licencias(df: pd.DataFrame) -> pd.DataFrame:
    t = pd.DataFrame({
        "registros": df["licencia"].value_counts(),
        "registros_mexico": df.loc[df["en_mexico"], "licencia"].value_counts(),
    }).fillna(0).astype(int)
    t = t.reindex([c for c in ORDEN if c in t.index] + [c for c in t.index if c not in ORDEN])
    t["pct_mexico"] = (t["registros_mexico"] / t["registros_mexico"].sum() * 100).round(1)
    return t


def main():
    df = leer()
    fuentes = tabla_fuentes(df)
    licencias = tabla_licencias(df)
    fuentes.to_csv(DESTINO / "fuentes_datos.csv", index=False, encoding="utf-8-sig")
    licencias.to_csv(DESTINO / "licencias_datos.csv", index_label="licencia",
                     encoding="utf-8-sig")
    print(f"{len(df):,} registros sin fosiles | {len(fuentes):,} fuentes "
          f"({fuentes['doi'].notna().sum():,} con DOI)")
    print(licencias.to_string())
    print(f"Salidas en {DESTINO}")


if __name__ == "__main__":
    main()
