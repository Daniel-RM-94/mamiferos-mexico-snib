"""Ejecuta el pipeline y los siete modulos de analisis, en orden.

Uso (desde la raiz del proyecto, con el Python del entorno virtual):
    .\\venv\\Scripts\\python.exe ejecutar_todo.py
    .\\venv\\Scripts\\python.exe ejecutar_todo.py --sin-pipeline        # reusa data/procesado
    .\\venv\\Scripts\\python.exe ejecutar_todo.py --solo mapas eoo_aoo
    .\\venv\\Scripts\\python.exe ejecutar_todo.py --continuar-si-falla

Cada paso corre como proceso aparte con el mismo interprete (y por lo tanto el
mismo venv) y con los parametros por defecto de su CLI. La salida de cada uno
se guarda en outputs/logs/<paso>.log.
"""
import argparse
import os
import subprocess
import sys
import time

from config import DIR_OUTPUTS, DIR_PROCESADO, RAIZ

PASOS = [
    ("pipeline", ["run_pipeline.py"], "ingesta, limpieza y enriquecimiento -> data/procesado"),
    ("comparativo", ["-m", "analisis.comparativo"], "riqueza, rarefaccion y diversidad beta"),
    ("mapas", ["-m", "analisis.mapas"], "mapas de celdas y mapa de especie"),
    ("conservacion", ["-m", "analisis.conservacion"], "NOM-059 x IUCN, ANP, exoticas"),
    ("uso_suelo", ["-m", "analisis.uso_suelo"], "series INEGI I-VII en los sitios"),
    ("temporal", ["-m", "analisis.temporal"], "inventario en el tiempo, estacionalidad"),
    ("gradientes", ["-m", "analisis.gradientes"], "latitud y altitud"),
    ("eoo_aoo", ["-m", "analisis.eoo_aoo"], "EOO, AOO y criterio B de la IUCN"),
]


def en_entorno_virtual() -> bool:
    return sys.prefix != sys.base_prefix


def ejecutar(nombre, argumentos, dir_logs) -> tuple[bool, float]:
    inicio = time.time()
    log = dir_logs / f"{nombre}.log"
    with open(log, "w", encoding="utf-8") as salida:
        proceso = subprocess.run(
            [sys.executable, *argumentos], cwd=RAIZ, stdout=salida, stderr=subprocess.STDOUT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return proceso.returncode == 0, time.time() - inicio


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sin-pipeline", action="store_true",
                        help="no regenera data/procesado (debe existir)")
    parser.add_argument("--solo", nargs="+", choices=[n for n, *_ in PASOS],
                        help="ejecuta solo estos pasos, en el orden de la lista")
    parser.add_argument("--continuar-si-falla", action="store_true")
    args = parser.parse_args()

    if not en_entorno_virtual():
        sys.exit("No se esta usando el entorno virtual. Ejecuta:\n"
                 "    .\\venv\\Scripts\\python.exe ejecutar_todo.py")

    pasos = [p for p in PASOS if (not args.solo or p[0] in args.solo)
             and not (args.sin_pipeline and p[0] == "pipeline")]
    if not pasos:
        sys.exit("No hay pasos que ejecutar con esa combinacion de opciones.")
    if not any(n == "pipeline" for n, *_ in pasos) and not DIR_PROCESADO.exists():
        sys.exit(f"No existe {DIR_PROCESADO}; corre primero el pipeline.")

    dir_logs = DIR_OUTPUTS / "logs"
    dir_logs.mkdir(parents=True, exist_ok=True)
    print(f"Python: {sys.executable}\n")

    resultados, total = [], time.time()
    for i, (nombre, argumentos, descripcion) in enumerate(pasos, 1):
        print(f"[{i}/{len(pasos)}] {nombre:<13} {descripcion} ...", end=" ", flush=True)
        ok, segundos = ejecutar(nombre, argumentos, dir_logs)
        resultados.append((nombre, ok, segundos))
        print(f"{'ok' if ok else 'FALLO'} ({segundos:.0f} s)")
        if not ok:
            print(f"    ver {dir_logs / f'{nombre}.log'}")
            if not args.continuar_si_falla:
                break

    fallidos = [n for n, ok, _ in resultados if not ok]
    print(f"\n{len(resultados) - len(fallidos)}/{len(pasos)} pasos correctos en "
          f"{time.time() - total:.0f} s. Resultados en {DIR_OUTPUTS}")
    sys.exit(1 if fallidos else 0)


if __name__ == "__main__":
    main()
