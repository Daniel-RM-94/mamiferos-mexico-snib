"""Conversion CSV -> Parquet de pipeline/convertir.py y su verificacion."""
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import pytest

from pipeline.convertir import convertir, verificar

CSV = (
    '"idejemplar","longitud","latitud","especievalida","anp"\n'
    '"a1","-100.123456789012","19.5","Romerolagus diazi",'
    '"Federal» Parques nacionales › Iztaccíhuatl-Popocatépetl"\n'
    '"a2","","","",""\n'
    '"a3","-87.1","20.25","Nasua narica nelsoni","NA"\n'
)


@pytest.fixture
def rutas(tmp_path):
    origen = tmp_path / "mamiferos.csv"
    origen.write_text(CSV, encoding="utf-8")
    return origen, tmp_path / "mamiferos.parquet"


def test_conversion_fiel(rutas):
    origen, destino = rutas
    tabla = convertir(origen, destino)
    assert verificar(origen, destino) == []
    assert tabla.schema.field("longitud").type == pa.float64()
    assert tabla.column("especievalida").to_pylist() == ["Romerolagus diazi", None,
                                                         "Nasua narica nelsoni"]
    assert tabla.column("anp").to_pylist()[2] == "NA"      # texto literal, no nulo


def test_verificacion_detecta_valores_alterados(rutas):
    origen, destino = rutas
    tabla = convertir(origen, destino)
    lat = pc.if_else(pc.equal(tabla.column("idejemplar"), "a3"), 20.2500001,
                     tabla.column("latitud"))
    pq.write_table(tabla.set_column(2, "latitud", lat), destino)
    assert verificar(origen, destino) == ["latitud: 1 valores distintos"]


def test_verificacion_detecta_filas_faltantes(rutas):
    origen, destino = rutas
    pq.write_table(convertir(origen, destino).slice(0, 2), destino)
    assert verificar(origen, destino) == ["filas: CSV 3 vs Parquet 2"]
