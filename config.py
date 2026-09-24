"""Configuracion central del pipeline de mamiferos (SNIB-CONABIO 2025-03)."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PARQUET_MAESTRO = RAIZ / "mamiferos.202503.parquet" / "mamiferos.parquet"
DIR_PROCESADO = RAIZ / "data" / "procesado"
DIR_OUTPUTS = RAIZ / "outputs"
# CSV por zona UTM (mamiferosutm<zona>.csv) del geoportal de CONABIO, version 2025-12;
# solo se usan para validar ZONAS_UTM (validar_zonas.py)
DIR_CSV_ZONAS = RAIZ / "data" / "crudo" / "snib_2025-12"

# Zonas UTM de Mexico: nombre -> (lon_oeste, lon_este], mismo criterio que los
# CSV mamiferosutm<zona>.csv de CONABIO (lon > oeste & lon <= este). Las siete
# zonas estan validadas contra esos CSV con validar_zonas.py.
# Deben ser contiguas y estar ordenadas de oeste a este.
ZONAS_UTM = {
    "11":  (-126, -114),
    "12":  (-114, -108),
    "13":  (-108, -102),
    "14a": (-102, -99),
    "14b": (-99, -96),
    "15":  (-96, -90),
    "16":  (-90, -84),
}
LAT_MEXICO = (12, 33)  # cubre todo el territorio y mar patrimonial registrado

CELDA_GRADOS = 0.25            # tamano de celda para mapas de riqueza/esfuerzo
INCERTIDUMBRE_CORTES_M = (1_000, 10_000)
ANIO_VALIDO = (1750, 2025)     # fuera de este rango aniocolecta se trata como nulo
ANIO_RECIENTE = 2000          # corte para "registro reciente"

NULO_SNIB = "\\N"  # el SNIB codifica los nulos como el texto literal \N

# Columnas que se leen del maestro (de 99). Leer todo cuesta ~2.2 GB de RAM.
COLUMNAS = [
    "idejemplar",
    # taxonomia
    "ordenvalido", "familiavalida", "generovalido", "especievalida",
    "subgrupobio", "nombrecomun", "taxonvalidado",
    # conservacion
    "nom059", "iucn", "cites", "endemismo", "prioritaria", "exoticainvasora",
    # geografia
    "longitud", "latitud", "altitudmapa", "incertidumbreXY", "geovalidacion",
    "paismapa", "estadomapa", "municipiomapa", "anp", "ambiente",
    # uso de suelo y vegetacion INEGI (serie I ~1985 ... serie VII ~2018)
    "usvserieI", "usvserieII", "usvserieIII", "usvserieIV",
    "usvserieV", "usvserieVI", "usvserieVII",
    # fecha y origen del registro
    "aniocolecta", "mescolecta", "diacolecta",
    "procedenciaejemplar", "institucion", "coleccion", "fuente",
]

# Especies no nativas que `exoticainvasora` no marca: fauna de zoologicos,
# ranchos cinegeticos (UMA) o mascotas. Se suman a las especies con al menos un
# registro marcado en `exoticainvasora` (la marca del SNIB no cubre todos los
# registros de una misma especie, p. ej. 11 de Bos taurus van sin marca).
ESPECIES_INTRODUCIDAS = [
    "Antidorcas marsupialis",   # gacela saltarina (Africa)
    "Apodemus sylvaticus",      # raton de campo (Eurasia)
    "Bos frontalis",            # gayal (Asia)
    "Boselaphus tragocamelus",  # nilgo (India)
    "Dama dama",                # gamo (Eurasia)
    "Erinaceus concolor",       # erizo (Eurasia)
    "Felis silvestris",         # gato montes europeo; en Mexico, gato domestico
    "Hippotragus equinus",      # antilope ruano (Africa)
    "Homo sapiens",
    "Litocranius walleri",      # gerenuk (Africa)
    "Melursus ursinus",         # oso bezudo (India)
    "Oryx beisa",               # orix (Africa)
    "Oryx gazella",             # orix del cabo (Africa)
    "Rhinoceros unicornis",     # rinoceronte indio
    "Rucervus duvaucelii",      # barasinga (India)
]

TIPO_REGISTRO = {
    "PreservedSpecimen": "Coleccion",
    "MaterialSample": "Coleccion",
    "MaterialCitation": "Coleccion",
    "LivingSpecimen": "Coleccion",
    "HumanObservation": "Observacion humana",
    "MachineObservation": "Observacion automatica",
}
