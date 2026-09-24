"""Guardado particionado y lectura filtrada de pipeline/io.py."""
from pipeline.enriquecer import enriquecer
from pipeline.io import cargar_procesado, guardar
from pipeline.limpieza import limpieza


def test_guardar_y_cargar_por_unidad(crear_registros, tmp_path):
    df = enriquecer(limpieza(crear_registros(
        {"longitud": -100.5},
        {"longitud": -97.0},
        {"longitud": -90.5, "latitud": 15.0, "paismapa": "GUATEMALA"},
    )))
    destino = tmp_path / "procesado"
    guardar(df, destino)

    assert sorted(p.name for p in destino.iterdir()) == \
        ["unidad=14a", "unidad=14b", "unidad=GUATEMALA"]
    todo = cargar_procesado(destino=destino)
    assert len(todo) == 3
    sub = cargar_procesado(["14b", "GUATEMALA"], columnas=["idejemplar", "unidad"],
                           destino=destino)
    assert sorted(sub["unidad"]) == ["14b", "GUATEMALA"]
    assert list(sub.columns) == ["idejemplar", "unidad"]
