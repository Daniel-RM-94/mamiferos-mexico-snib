"""Decisiones de depuracion de pipeline/limpieza.py (ver README, seccion 'Decisiones')."""
import numpy as np
import pandas as pd

from pipeline.limpieza import limpieza, valor_nivel_especie


def test_nulo_snib_se_convierte_en_nulo_real(crear_registros):
    df = limpieza(crear_registros({"nombrecomun": "\\N", "estadomapa": ""}))
    assert df["nombrecomun"].isna().all()
    assert df["estadomapa"].isna().all()


def test_valores_numericos_fuera_de_rango_son_nulos(crear_registros):
    df = limpieza(crear_registros(
        {"altitudmapa": "7000", "aniocolecta": "1600", "mescolecta": "13", "diacolecta": "0"},
        {"altitudmapa": "abc", "incertidumbreXY": "-5"},
    ))
    assert df["altitud_m"].isna().all()
    assert df.loc[0, ["anio", "mes", "dia"]].isna().all()
    assert pd.isna(df.at[1, "incertidumbre_m"])


def test_subgenero_se_elimina_del_nombre(crear_registros):
    df = limpieza(crear_registros(
        {"especievalida": "Artibeus (Dermanura) glaucus"},
        {"especievalida": "Artibeus glaucus"},
    ))
    assert df["especie"].tolist() == ["Artibeus glaucus", "Artibeus glaucus"]
    assert df["subespecie"].isna().all()


def test_trinomio_separa_especie_y_subespecie(crear_registros):
    df = limpieza(crear_registros({"especievalida": "Nasua narica nelsoni"}))
    assert df.at[0, "especie"] == "Nasua narica"
    assert df.at[0, "subespecie"] == "nelsoni"


def test_nivel_taxonomico_sin_especie(crear_registros):
    df = limpieza(crear_registros(
        {},
        {"especievalida": "\\N"},
        {"especievalida": "\\N", "generovalido": "\\N"},
    ))
    assert df["nivel_taxonomico"].tolist() == ["especie", "genero", "familia"]


def test_codigos_de_riesgo_se_extraen_del_texto(crear_registros):
    df = limpieza(crear_registros({
        "nom059": "Amenazada (A) (Publicado en NOM-059-SEMARNAT-2010 como Sorex sp.)",
        "iucn": "Vulnerable (VU)",
        "cites": "Apéndice II",
    }))
    assert df.at[0, "nom059_cod"] == "A"
    assert df.at[0, "iucn_cod"] == "VU"
    assert df.at[0, "cites_cod"] == "II"
    assert df.at[0, "en_nom059"] and df.at[0, "iucn_amenazada"]


def test_endemismo_de_subespecie_no_se_hereda_a_la_especie(crear_registros):
    # Nasua narica nelsoni (Cozumel) es endemica; Nasua narica no lo es
    df = limpieza(crear_registros(
        {"especievalida": "Nasua narica nelsoni", "endemismo": "Endémica"},
        {"especievalida": "Nasua narica"},
        {"especievalida": "Nasua narica"},
    ))
    assert df.at[0, "endemica"]
    assert not df["endemica_especie"].any()


def test_endemismo_solo_se_toma_de_registros_de_mexico(crear_registros):
    df = limpieza(crear_registros(
        {"especievalida": "Romerolagus diazi", "endemismo": "Endémica"},
        {"especievalida": "Romerolagus diazi", "paismapa": "ESTADOS UNIDOS DE AMERICA"},
        {"especievalida": "Romerolagus diazi", "paismapa": "ESTADOS UNIDOS DE AMERICA"},
    ))
    assert df["endemica_especie"].all()


def test_valor_nivel_especie_usa_registros_sin_subespecie():
    df = pd.DataFrame({
        "especie": ["A b", "A b", "A b", "C d", "C d", "E f", "E f"],
        "subespecie": [np.nan, np.nan, "x", "x", "y", "x", "x"],
        "col": ["LC", "LC", "EN", "VU", "EN", "NT", "NT"],
    })
    v = valor_nivel_especie(df, "col")
    assert v["A b"] == "LC"          # la subespecie EN no cuenta
    assert pd.isna(v["C d"])         # solo subespecies y no coinciden
    assert v["E f"] == "NT"          # solo subespecies y coinciden


def test_marinos_por_taxonomia_aunque_falte_ambiente(crear_registros):
    df = limpieza(crear_registros(
        {"ordenvalido": "Cetacea", "ambiente": "\\N"},
        {"ordenvalido": "Carnivora", "familiavalida": "Otariidae", "ambiente": "\\N"},
        {"ambiente": "Marino"},
        {"ambiente": "Marino, Terrestre"},
    ))
    assert df["es_marino"].tolist() == [True, True, True, False]


def test_exotica_se_propaga_a_toda_la_especie(crear_registros):
    df = limpieza(crear_registros(
        {"especievalida": "Bos taurus", "exoticainvasora": "Exótica"},
        {"especievalida": "Bos taurus"},
        {"especievalida": "Dama dama"},       # config.ESPECIES_INTRODUCIDAS
        {},
    ))
    assert df["es_exotica"].tolist() == [True, True, True, False]


def test_anp_con_distancia_es_fuera(crear_registros):
    df = limpieza(crear_registros(
        {"anp": "Federal» Áreas de protección de flora y fauna › Janos"},
        {"anp": "Estatal» Parque Estatal › Sierra de Guadalupe: Polígono 1 (México) {a 1.183 km}"},
        {"anp": "Estatal» Reserva Estatal › Sierra {a 2.5 km} | "
                "Federal» Reservas de la biosfera › Calakmul"},
        {},
    ))
    assert df["dentro_anp"].tolist() == [True, False, True, False]
    assert df.at[0, "anp_nombre"] == "Janos"
    assert df.at[0, "anp_categoria"] == "Áreas de protección de flora y fauna"
    assert pd.isna(df.at[1, "anp_nombre"])
    assert df.at[2, "anp_nombre"] == "Calakmul"
    assert df.at[2, "anp_tipo"] == "Federal"
    assert df.at[0, "anp_distancia_km"] == 0.0
    assert df.at[1, "anp_distancia_km"] == 1.183
    assert pd.isna(df.at[3, "anp_distancia_km"])


def test_anp_formato_sin_categoria(crear_registros):
    # versiones anteriores a 2025-12: "Tipo» Nombre", sin categoria
    df = limpieza(crear_registros({"anp": "Federal» Janos"}))
    assert df.at[0, "anp_nombre"] == "Janos"
    assert pd.isna(df.at[0, "anp_categoria"])


def test_duplicado_de_evento_marca_solo_repeticiones(crear_registros):
    df = limpieza(crear_registros(
        {},
        {},                                   # mismo taxon, punto y fecha
        {"diacolecta": "16"},                 # otro dia
        {"especievalida": "Peromyscus levipes"},
    ))
    assert df["dup_evento"].tolist() == [False, True, False, False]
    assert len(df) == 4                       # se conservan como ejemplares
