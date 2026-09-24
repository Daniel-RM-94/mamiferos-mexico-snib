"""Ejecuta las etapas 01-04: ingesta -> limpieza -> enriquecimiento -> guardado.

Uso:  python run_pipeline.py
Salida: data/procesado/unidad=<zona o pais>/*.parquet
        outputs/tablas/resumen_unidades.csv
"""
import time

from analisis.comparativo import tabla_resumen
from config import DIR_OUTPUTS, DIR_PROCESADO
from pipeline.enriquecer import enriquecer
from pipeline.ingesta import ingesta
from pipeline.io import guardar
from pipeline.limpieza import limpieza


def _paso(nombre, funcion, *args):
    t = time.time()
    resultado = funcion(*args)
    print(f"[{nombre}] {len(resultado):,} filas  ({time.time() - t:.1f} s)")
    return resultado


def main():
    t0 = time.time()
    df = _paso("01 ingesta", ingesta)
    df = _paso("02 limpieza", limpieza, df)
    df = _paso("03 enriquecer", enriquecer, df)

    print(f"    marcados dup_evento: {df['dup_evento'].sum():,}")
    print(f"    especies exoticas: {df.loc[df['es_exotica'], 'especie'].nunique()} "
          f"({df['es_exotica'].sum():,} registros)")
    print(f"    registros dentro de un ANP: {df['dentro_anp'].sum():,} "
          f"(otros {(df['anp'].notna() & ~df['dentro_anp']).sum():,} solo cerca)")
    print(f"    registros a nivel especie: {(df['nivel_taxonomico'] == 'especie').mean():.1%}")
    print(f"    Mexico sin zona UTM asignada: "
          f"{((df['paismapa'] == 'MEXICO') & df['zona_utm'].isna()).sum():,}")

    t = time.time()
    guardar(df)
    print(f"[04 guardar] {DIR_PROCESADO}  ({time.time() - t:.1f} s)")

    resumen = tabla_resumen(df).sort_values("registros", ascending=False)
    (DIR_OUTPUTS / "tablas").mkdir(parents=True, exist_ok=True)
    resumen.to_csv(DIR_OUTPUTS / "tablas" / "resumen_unidades.csv", encoding="utf-8-sig")

    zonas = resumen.loc[resumen.index.isin(df["zona_utm"].cat.categories)]
    print("\nResumen por zona UTM de Mexico:")
    print(zonas.sort_index().to_string())
    print(f"\nTotal: {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
