"""Etapa 00: convierte el CSV del SNIB a Parquet y verifica que la conversion sea fiel.

El CSV completo (mamiferos.csv, ~1.7 GB) se descarga del geoportal de CONABIO. Se
convierte una sola vez: todos los campos se guardan como texto, salvo longitud y
latitud (float64); las celdas vacias del CSV quedan como nulos.

La verificacion vuelve a leer el CSV con un lector independiente (todo como texto,
sin interpretar nulos) y compara con el Parquet columna por columna:
    - mismas columnas, en el mismo orden, y mismo numero de filas;
    - idejemplar unicos;
    - texto identico (nulo del Parquet == celda vacia del CSV);
    - longitud y latitud identicas al leer el texto del CSV como float64.
Ademas escribe un manifiesto JSON con el SHA-256 del CSV de origen.

Uso:
    .\\venv\\Scripts\\python.exe -m pipeline.convertir
    .\\venv\\Scripts\\python.exe -m pipeline.convertir --solo-verificar
"""
import argparse
import hashlib
import json
import sys
from datetime import date

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pcsv
import pyarrow.parquet as pq

from config import CSV_MAESTRO, PARQUET_MAESTRO, VERSION_SNIB

NUMERICAS = {"longitud": pa.float64(), "latitud": pa.float64()}


def _columnas(ruta):
    return pcsv.open_csv(ruta).schema.names


def convertir(origen=CSV_MAESTRO, destino=PARQUET_MAESTRO) -> pa.Table:
    tipos = {c: NUMERICAS.get(c, pa.string()) for c in _columnas(origen)}
    tabla = pcsv.read_csv(origen, convert_options=pcsv.ConvertOptions(
        column_types=tipos, null_values=[""], strings_can_be_null=True))
    pq.write_table(tabla, destino, compression="zstd")
    return tabla


def verificar(origen=CSV_MAESTRO, destino=PARQUET_MAESTRO) -> list[str]:
    """Lista de problemas encontrados (vacia si la conversion es fiel)."""
    texto = pcsv.read_csv(origen, convert_options=pcsv.ConvertOptions(
        column_types={c: pa.string() for c in _columnas(origen)},
        strings_can_be_null=False, quoted_strings_can_be_null=False))
    parquet = pq.read_table(destino)
    problemas = []
    if texto.column_names != parquet.column_names:
        problemas.append("las columnas o su orden no coinciden")
        return problemas
    if texto.num_rows != parquet.num_rows:
        problemas.append(f"filas: CSV {texto.num_rows:,} vs Parquet {parquet.num_rows:,}")
        return problemas
    ids = parquet.column("idejemplar")
    if pc.count_distinct(ids).as_py() != parquet.num_rows or ids.null_count:
        problemas.append("idejemplar nulos o repetidos")

    for c in texto.column_names:
        esperado = texto.column(c)
        obtenido = parquet.column(c)
        if c in NUMERICAS:
            esperado = pc.cast(pc.if_else(pc.equal(esperado, ""), None, esperado), NUMERICAS[c])
            iguales = pc.or_kleene(pc.equal(esperado, obtenido),
                                   pc.and_(pc.is_null(esperado), pc.is_null(obtenido)))
        else:
            iguales = pc.equal(esperado, pc.fill_null(obtenido, ""))
        n_dif = parquet.num_rows - pc.sum(pc.cast(pc.fill_null(iguales, False), pa.int64())).as_py()
        if n_dif:
            problemas.append(f"{c}: {n_dif:,} valores distintos")
    return problemas


def sha256(ruta, bloque=1 << 24) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        while datos := f.read(bloque):
            h.update(datos)
    return h.hexdigest()


def manifiesto(origen=CSV_MAESTRO, destino=PARQUET_MAESTRO) -> dict:
    meta = pq.read_metadata(destino)
    versiones = pc.unique(pq.read_table(destino, columns=["version"]).column("version"))
    info = {
        "origen": origen.name,
        "origen_bytes": origen.stat().st_size,
        "origen_sha256": sha256(origen),
        "version_snib": [v for v in versiones.to_pylist() if v],
        "registros": meta.num_rows,
        "columnas": meta.num_columns,
        "convertido": date.today().isoformat(),
    }
    destino.with_suffix(".json").write_text(json.dumps(info, indent=2, ensure_ascii=False),
                                            encoding="utf-8")
    return info


def main(solo_verificar=False) -> int:
    if not solo_verificar:
        print(f"Convirtiendo {CSV_MAESTRO.name} -> {PARQUET_MAESTRO.name} ...")
        convertir()
    problemas = verificar()
    if problemas:
        print("La conversion NO es fiel:\n  " + "\n  ".join(problemas))
        return 1
    info = manifiesto()
    print(f"Conversion fiel: {info['registros']:,} registros x {info['columnas']} columnas, "
          f"version SNIB {', '.join(info['version_snib'])} (esperada {VERSION_SNIB})")
    print(f"SHA-256 del CSV: {info['origen_sha256']}")
    return 0 if info["version_snib"] == [VERSION_SNIB] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--solo-verificar", action="store_true",
                        help="no convierte; solo compara el Parquet existente con el CSV")
    sys.exit(main(parser.parse_args().solo_verificar))
