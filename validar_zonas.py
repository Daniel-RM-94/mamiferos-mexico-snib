"""Valida los limites de config.ZONAS_UTM contra los CSV por zona de CONABIO.

Los CSV (mamiferosutm<zona>.csv, uno por zona) se descargan del geoportal de
CONABIO, se guardan en config.DIR_CSV_ZONAS y no se versionan. Pueden ser de
una version del SNIB distinta a la del Parquet maestro, por lo que la validacion
no exige que coincidan los idejemplar 1:1:

1. Regla geografica: cada registro de un CSV debe caer, por su longitud, latitud
   y paismapa, en la zona de su archivo segun pipeline.enriquecer.asignar_zona.
2. Registros comunes: los idejemplar presentes en el maestro y en algun CSV deben
   quedar en la misma zona en ambos.

Uso:
    .\\venv\\Scripts\\python.exe validar_zonas.py              # CSV en config.DIR_CSV_ZONAS
    .\\venv\\Scripts\\python.exe validar_zonas.py --dir otra/carpeta
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds

from config import DIR_CSV_ZONAS, PARQUET_MAESTRO, ZONAS_UTM
from pipeline.enriquecer import asignar_zona


def leer_csv(directorio: Path) -> pd.DataFrame:
    partes = []
    for zona in ZONAS_UTM:
        archivo = directorio / f"mamiferosutm{zona}.csv"
        if archivo.exists():
            c = pd.read_csv(archivo, dtype=str, usecols=["idejemplar", "longitud", "latitud",
                                                         "paismapa", "version"])
            partes.append(c.assign(archivo=zona))
    if not partes:
        sys.exit(f"No hay archivos mamiferosutm<zona>.csv en {directorio}")
    df = pd.concat(partes, ignore_index=True)
    df["paismapa"] = df["paismapa"].replace("\\N", pd.NA)
    df["zona"] = asignar_zona(pd.to_numeric(df["longitud"], errors="coerce"),
                              pd.to_numeric(df["latitud"], errors="coerce"),
                              df["paismapa"]).astype(object)
    return df


def main(directorio: Path) -> int:
    csv = leer_csv(directorio)
    zonas = sorted(csv["archivo"].unique(), key=list(ZONAS_UTM).index)
    print(f"CSV: zonas {', '.join(zonas)} | {len(csv):,} registros | "
          f"version SNIB {', '.join(csv['version'].dropna().unique())}")

    # 1. Regla geografica sobre los registros de CONABIO
    distinta = csv[csv["zona"] != csv["archivo"]]
    print("\n1. Regla geografica (registros del CSV en la zona de su archivo)")
    for zona, g in csv.groupby("archivo", sort=False):
        n_mal = (g["zona"] != zona).sum()
        print(f"   {zona:>3}: {len(g) - n_mal:>9,} de {len(g):>9,}")
    if len(distinta):
        print("   Excepciones:")
        print(distinta[["archivo", "idejemplar", "longitud", "latitud", "paismapa", "zona"]]
              .to_string(index=False))

    # 2. Registros comunes con el maestro
    m = ds.dataset(PARQUET_MAESTRO).to_table(
        columns=["idejemplar", "longitud", "latitud", "paismapa", "version"]).to_pandas()
    m["zona"] = asignar_zona(m["longitud"], m["latitud"], m["paismapa"]).astype(object)
    m = m[m["zona"].isin(zonas)]
    comunes = m.merge(csv[["idejemplar", "archivo"]], on="idejemplar")
    cambian = comunes[comunes["zona"] != comunes["archivo"]]
    print(f"\n2. Registros comunes con el maestro (version {', '.join(m['version'].unique())})")
    print(f"   {len(comunes):,} de {len(m):,} registros del maestro en estas zonas tienen su "
          f"idejemplar en los CSV; {len(cambian):,} cambian de zona")
    print(f"   {len(m) - len(comunes):,} no estan en los CSV (altas y bajas entre versiones)")

    ok = len(cambian) == 0 and len(distinta) <= len(csv) * 1e-4
    print("\nResultado:", "limites validados" if ok else "REVISAR config.ZONAS_UTM")
    return 0 if ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dir", type=Path, default=DIR_CSV_ZONAS,
                        help="carpeta con los mamiferosutm<zona>.csv "
                             "(por defecto, config.DIR_CSV_ZONAS)")
    sys.exit(main(parser.parse_args().dir))
