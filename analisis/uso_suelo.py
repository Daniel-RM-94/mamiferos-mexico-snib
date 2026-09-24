"""Uso de suelo y vegetacion (INEGI series I-VII) en los puntos de registro.

Uso:
    python -m analisis.uso_suelo

Salidas en outputs/uso_suelo/:
    clases_usv.csv                 como se agrupo cada una de las ~345 clases INEGI
    especializacion.csv / .png     E1: amplitud de nicho por formacion vegetal
    tolerancia.csv / .png          E2: % de registros en suelo agricola, pecuario o urbano
    transiciones_I_VII.csv / .png  E3: condicion del punto en la serie I vs la VII
    antropizacion_zonas.csv / .png E3: % de puntos transformados por zona y serie
    perdida_especies.csv / .png    E3: puntos de cada especie que eran vegetacion
                                   natural en la serie I y hoy son uso antropico

Cada registro trae la clase INEGI de su punto en las 7 series. Para E1 y E2 se
usa la serie mas cercana al ano de colecta (uso de suelo contemporaneo al
registro); para E3 se comparan las series I (~1985) y VII (~2018) sobre puntos
unicos, para que un sitio muy colectado no pese mas que otro.

Limitaciones: los puntos de registro no son una muestra aleatoria del paisaje
(se colecta cerca de caminos y poblados); la cartografia es 1:250,000 y los
metodos de INEGI cambiaron entre series. Se excluyen registros con
incertidumbre conocida mayor a MAX_INCERTIDUMBRE_M.
"""
import argparse
import re
import unicodedata

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analisis import estilo
from config import DIR_OUTPUTS, ZONAS_UTM
from pipeline.io import cargar_procesado

SALIDA = DIR_OUTPUTS / "uso_suelo"
SERIES = {  # columna -> (etiqueta, ano de referencia aproximado de la cartografia)
    "usvserieI": ("I", 1985), "usvserieII": ("II", 1993), "usvserieIII": ("III", 2002),
    "usvserieIV": ("IV", 2008), "usvserieV": ("V", 2013), "usvserieVI": ("VI", 2016),
    "usvserieVII": ("VII", 2018),
}
MAX_INCERTIDUMBRE_M = 1_000
DECIMALES_PUNTO = 3            # ~110 m: puntos a menos de esa distancia son el mismo sitio
MIN_REGISTROS_ESPECIE = 30     # E1 y E2
MIN_PUNTOS_ESPECIE = 20        # E3
UMBRAL_ESPECIALISTA = 0.7      # >= 70 % de registros en una formacion

CONDICIONES = ["Primaria", "Secundaria", "Pastizal o bosque inducido",
               "Agrícola", "Urbana", "Agua o sin vegetación"]
NATURAL = ["Primaria", "Secundaria"]
ANTROPICA = ["Pastizal o bosque inducido", "Agrícola", "Urbana"]
FORMACIONES = ["Bosque de coníferas", "Bosque de encino", "Bosque mesófilo",
               "Selva perennifolia", "Selva caducifolia", "Matorral xerófilo",
               "Pastizal natural", "Vegetación hidrófila", "Otros tipos"]
COLUMNAS = list(SERIES) + ["especie", "unidad", "longitud", "latitud", "anio",
                           "incertidumbre_m", "endemica_especie", "en_nom059", "iucn_amenazada",
                           "nom059_cod", "iucn_cod", "es_marino", "es_exotica", "dup_evento"]


# ─────────────────────────────────────────
# Clasificacion de las clases INEGI
# ─────────────────────────────────────────

def _sin_acentos(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn").upper().strip()


def _formacion(base):
    if "MESOFILO" in base:
        return "Bosque mesófilo"
    if base.startswith("BOSQUE DE ENCINO"):                      # incluye encino-pino
        return "Bosque de encino"
    if base.startswith(("BOSQUE DE PINO", "BOSQUE DE OYAMEL", "BOSQUE DE AYARIN",
                        "BOSQUE DE CEDRO", "BOSQUE DE TASCATE", "MATORRAL DE CONIFERAS")):
        return "Bosque de coníferas"
    if "GALERIA" in base or base.startswith(("MANGLAR", "TULAR", "POPAL", "VEGETACION DE PETEN",
                                             "VEGETACION HALOFILA HIDROFILA")):
        return "Vegetación hidrófila"
    if base.startswith("SELVA"):
        if "ESPINOSA" not in base and "PERENNIFOLIA" in base:   # incluye subperennifolia
            return "Selva perennifolia"
        return "Selva caducifolia"                               # sub/caducifolia y espinosa
    if base.startswith("MEZQUITAL TROPICAL"):
        return "Selva caducifolia"
    if base.startswith(("MATORRAL", "MEZQUITAL", "HUIZACHAL", "CHAPARRAL",
                        "BOSQUE DE MEZQUITE", "VEGETACION DE DESIERTOS")):
        return "Matorral xerófilo"
    if base.startswith(("PASTIZAL", "SABANA", "PRADERA")):
        return "Pastizal natural"
    if base.startswith(("VEGETACION DE DUNAS", "VEGETACION HALOFILA", "VEGETACION GIPSOFILA",
                        "PALMAR NATURAL", "BOSQUE BAJO ABIERTO")):
        return "Otros tipos"
    return None


def clasificar_clase(valor):
    """Clase INEGI -> (condicion, formacion). La vegetacion secundaria conserva
    la formacion de la que proviene; los usos antropicos no tienen formacion."""
    if pd.isna(valor) or valor == "NO EMPATA":
        return None, None
    t = _sin_acentos(valor)
    if t.startswith(("ZONA URBANA", "ASENTAMIENTOS", "URBANO")):
        return "Urbana", None
    if t.startswith(("AGRICULTURA", "AREAS DE RIEGO", "ACUICOLA")):
        return "Agrícola", None
    if t.startswith(("PASTIZAL CULTIVADO", "PASTIZAL INDUCIDO", "BOSQUE CULTIVADO",
                     "BOSQUE INDUCIDO", "PALMAR INDUCIDO", "SABANOIDE")):
        return "Pastizal o bosque inducido", None
    if t.startswith(("CUERPO DE AGUA", "AGUA", "DESPROVISTO", "SIN VEGETACION",
                     "AREA DESPROVISTA", "SALINAS")):
        return "Agua o sin vegetación", None
    if t.startswith("VEGETACION SECUNDARIA"):
        base = re.sub(r"^VEGETACION SECUNDARIA (ARBUSTIVA|ARBOREA|HERBACEA) DE ", "", t)
        return "Secundaria", _formacion(base)
    if "AGRICULTURA NOMADA" in t:          # serie I: vegetacion con agricultura de roza
        return "Secundaria", _formacion(t)
    formacion = _formacion(t)
    return ("Primaria", formacion) if formacion else (None, None)


def tabla_clases(df: pd.DataFrame) -> pd.DataFrame:
    valores = pd.unique(pd.concat([df[c].astype(object) for c in SERIES]).dropna())
    filas = [(v, *clasificar_clase(v)) for v in valores]
    return (pd.DataFrame(filas, columns=["clase_inegi", "condicion", "formacion"])
            .sort_values("clase_inegi").reset_index(drop=True))


def _categorias(serie, categorias):
    return pd.Categorical(serie, categories=categorias, ordered=True)


def preparar(unidades) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = cargar_procesado(unidades, columnas=COLUMNAS)
    df = df[df["especie"].notna() & ~df["dup_evento"] & ~df["es_marino"] & ~df["es_exotica"]]
    df = df[~(df["incertidumbre_m"] > MAX_INCERTIDUMBRE_M)].copy()   # NaN se conserva

    clases = tabla_clases(df)
    cond = dict(zip(clases["clase_inegi"], clases["condicion"]))
    form = dict(zip(clases["clase_inegi"], clases["formacion"]))
    for col, (etiqueta, _) in SERIES.items():
        texto = df[col].astype(object)
        df[f"cond_{etiqueta}"] = _categorias(texto.map(cond), CONDICIONES)
        df[f"form_{etiqueta}"] = _categorias(texto.map(form), FORMACIONES)

    # Serie contemporanea: la de ano de referencia mas cercano al ano de colecta
    anios = np.array([a for _, a in SERIES.values()])
    etiquetas = [e for e, _ in SERIES.values()]
    anio = df["anio"].astype(float).to_numpy()
    cercana = np.abs(np.nan_to_num(anio)[:, None] - anios[None, :]).argmin(axis=1)
    for prefijo, categorias in [("cond", CONDICIONES), ("form", FORMACIONES)]:
        matriz = np.column_stack([df[f"{prefijo}_{e}"].astype(object).to_numpy()
                                  for e in etiquetas])
        valor = matriz[np.arange(len(df)), cercana]
        valor[np.isnan(anio)] = None
        df[f"{prefijo}_contemp"] = _categorias(valor, categorias)

    df["punto"] = (df["longitud"].round(DECIMALES_PUNTO).astype(str) + ","
                   + df["latitud"].round(DECIMALES_PUNTO).astype(str))
    df["en_riesgo"] = df["en_nom059"] | df["iucn_amenazada"]
    return df, clases


def estatus_especies(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("especie")
    return pd.DataFrame({
        "endemica": g["endemica_especie"].first(),
        "en_riesgo": g["en_riesgo"].any(),
        "nom059_max": g["nom059_cod"].max(),
        "iucn_max": g["iucn_cod"].max(),
    })


def _etiqueta_especie(nombre, estatus):
    fila = estatus.loc[nombre]
    codigos = "/".join(str(v) for v in (fila["nom059_max"], fila["iucn_max"]) if pd.notna(v))
    marca = " *" if fila["endemica"] else ""
    return f"{estilo.cursiva(nombre)}{marca}" + (f"  ({codigos})" if codigos else "")


# ─────────────────────────────────────────
# E1. Especializacion por formacion vegetal
# ─────────────────────────────────────────

def especializacion(df: pd.DataFrame, estatus: pd.DataFrame) -> pd.DataFrame:
    """Amplitud de nicho de Levins estandarizada sobre las formaciones:
    B_A = (1 / sum(p_i^2) - 1) / (n - 1); 0 = especialista, 1 = generalista."""
    sub = df[df["form_contemp"].notna()]
    tabla = pd.crosstab(sub["especie"], sub["form_contemp"]).reindex(columns=FORMACIONES,
                                                                     fill_value=0)
    tabla = tabla[tabla.sum(axis=1) >= MIN_REGISTROS_ESPECIE]
    p = tabla.div(tabla.sum(axis=1), axis=0)
    resultado = pd.DataFrame({
        "registros": tabla.sum(axis=1),
        "formacion_principal": p.idxmax(axis=1),
        "pct_formacion_principal": (p.max(axis=1) * 100).round(1),
        "amplitud_levins": ((1 / (p ** 2).sum(axis=1) - 1) / (len(FORMACIONES) - 1)).round(3),
    }).join(estatus).join((p * 100).round(1).add_prefix("pct_"))
    resultado["especialista"] = resultado["pct_formacion_principal"] >= UMBRAL_ESPECIALISTA * 100
    return resultado.sort_values("amplitud_levins")


def fig_especialistas(esp, destino):
    especialistas = esp[esp["especialista"]]
    conteo = pd.crosstab(especialistas["formacion_principal"], especialistas["en_riesgo"])
    conteo = conteo.reindex(index=FORMACIONES, columns=[True, False], fill_value=0)
    conteo = conteo[conteo.sum(axis=1) > 0]
    conteo = conteo.loc[conteo.sum(axis=1).sort_values().index]
    y = np.arange(len(conteo))
    fig, ax = plt.subplots(figsize=(8.5, 0.5 * len(conteo) + 1.8))
    ax.barh(y, conteo[True], height=0.6, color=estilo.CATEGORICA[1], label="En riesgo")
    ax.barh(y, conteo[False], left=conteo[True], height=0.6, color=estilo.CATEGORICA[0],
            edgecolor=estilo.SUPERFICIE, linewidth=2, label="Sin categoría de riesgo")
    for yi, total in zip(y, conteo.sum(axis=1)):
        ax.annotate(f"{total}", (total, yi), xytext=(4, 0), textcoords="offset points",
                    va="center", fontsize=8.5, color=estilo.TINTA_2)
    ax.set_yticks(y, conteo.index)
    ax.set_xlabel("Especies especialistas")
    ax.grid(axis="y", visible=False)
    ax.set_title(f"Especies con ≥ {UMBRAL_ESPECIALISTA:.0%} de sus registros en una formación",
                 pad=30)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncols=2, borderaxespad=0.3)
    fig.savefig(destino)
    plt.close(fig)


# ─────────────────────────────────────────
# E2. Tolerancia a ambientes transformados
# ─────────────────────────────────────────

def tolerancia(df: pd.DataFrame, estatus: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    sub = df[df["cond_contemp"].notna() & (df["cond_contemp"] != "Agua o sin vegetación")]
    antropica = sub["cond_contemp"].isin(ANTROPICA)
    base = antropica.mean() * 100
    g = antropica.groupby(sub["especie"])
    t = pd.DataFrame({"registros": g.size(), "pct_antropico": (g.mean() * 100).round(1)})
    for cond in ANTROPICA:
        t[f"pct_{cond.split()[0].lower()}"] = (
            sub["cond_contemp"].eq(cond).groupby(sub["especie"]).mean() * 100).round(1)
    t = t[t["registros"] >= MIN_REGISTROS_ESPECIE].join(estatus)
    t["razon_vs_base"] = (t["pct_antropico"] / base).round(2)
    return t.sort_values("pct_antropico", ascending=False), base


def fig_tolerancia(t, base, estatus, destino, top=25):
    datos = t.head(top).iloc[::-1]
    y = np.arange(len(datos))
    fig, ax = plt.subplots(figsize=(9, 0.32 * len(datos) + 1.8))
    ax.barh(y, datos["pct_antropico"], height=0.6, color=estilo.AZUL)
    for yi, v in zip(y, datos["pct_antropico"]):
        ax.annotate(f"{v:.0f} %", (v, yi), xytext=(4, 0), textcoords="offset points",
                    va="center", fontsize=8, color=estilo.TINTA_2)
    ax.axvline(base, color=estilo.TINTA_2, linewidth=1)
    ax.annotate(f"todas las especies: {base:.0f} %", (base, len(datos) - 0.4),
                xytext=(4, 0), textcoords="offset points", fontsize=8.5,
                color=estilo.TINTA_2, va="bottom")
    ax.set_yticks(y, [_etiqueta_especie(e, estatus) for e in datos.index], fontsize=8.5)
    ax.set_xlim(0, 100)
    ax.set_xlabel("% de registros en suelo agrícola, pecuario o urbano (uso contemporáneo)")
    ax.grid(axis="y", visible=False)
    ax.set_title(f"Especies con más registros en ambientes transformados\n"
                 f"(≥ {MIN_REGISTROS_ESPECIE} registros; * endémica; NOM-059/IUCN)")
    fig.savefig(destino)
    plt.close(fig)


# ─────────────────────────────────────────
# E3. Cambio de uso de suelo en los puntos (serie I -> serie VII)
# ─────────────────────────────────────────

def puntos_unicos(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["punto", "unidad"] + [f"cond_{e}" for e, _ in SERIES.values()]
    return df[cols].drop_duplicates("punto")


def transiciones(puntos: pd.DataFrame) -> pd.DataFrame:
    sub = puntos[puntos["cond_I"].notna() & puntos["cond_VII"].notna()]
    return pd.crosstab(sub["cond_I"], sub["cond_VII"]).reindex(
        index=CONDICIONES, columns=CONDICIONES, fill_value=0)


def antropizacion_zonas(puntos: pd.DataFrame, unidades) -> pd.DataFrame:
    filas = {}
    for etiqueta, _ in SERIES.values():
        col = puntos[f"cond_{etiqueta}"]
        validos = col.notna()
        filas[etiqueta] = (col[validos].isin(ANTROPICA)
                           .groupby(puntos.loc[validos, "unidad"]).mean() * 100)
    return pd.DataFrame(filas).reindex(unidades).round(1)


def perdida_especies(df: pd.DataFrame, estatus: pd.DataFrame) -> pd.DataFrame:
    pts = df[["especie", "punto", "cond_I", "cond_VII"]].drop_duplicates(["especie", "punto"])
    pts = pts[pts["cond_I"].isin(NATURAL) & pts["cond_VII"].notna()]
    g = pts.groupby("especie")
    t = pd.DataFrame({
        "puntos_naturales_serie_I": g.size(),
        "pct_a_antropico": (g["cond_VII"].agg(lambda s: s.isin(ANTROPICA).mean()) * 100).round(1),
        "pct_primaria_a_secundaria": (
            pts.assign(deg=(pts["cond_I"] == "Primaria") & (pts["cond_VII"] == "Secundaria"))
            .groupby("especie")["deg"].mean() * 100).round(1),
    })
    t = t[t["puntos_naturales_serie_I"] >= MIN_PUNTOS_ESPECIE].join(estatus)
    return t.sort_values("pct_a_antropico", ascending=False)


def fig_transiciones(tr, destino):
    pct = tr.div(tr.sum(axis=1).replace(0, np.nan), axis=0).fillna(0) * 100
    pct.index = [f"{c}  (n = {n:,})" for c, n in zip(tr.index, tr.sum(axis=1))]
    fig, ax = plt.subplots(figsize=(11, 4.6))
    im = estilo.heatmap(ax, pct, ".0f", vmax=100)
    ax.set_xticks(range(len(CONDICIONES)),
                  [c.replace(" o ", " o\n") for c in CONDICIONES], fontsize=9)
    ax.set_xlabel("Serie VII (~2018)")
    ax.set_ylabel("Serie I (~1985)")
    ax.set_title("Condición de los puntos de registro: serie I → serie VII "
                 "(% de cada fila; puntos únicos)")
    fig.colorbar(im, ax=ax, shrink=0.8, label="% de los puntos").outline.set_visible(False)
    fig.savefig(destino)
    plt.close(fig)


def fig_antropizacion(t, destino):
    colores = estilo.colores_unidades(list(t.index))
    anios = [a for _, a in SERIES.values()]
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for zona, fila in t.iterrows():
        ax.plot(anios, fila.to_numpy(), color=colores[zona], label=zona, marker="o",
                markersize=5, markeredgecolor=estilo.SUPERFICIE, markeredgewidth=1.5)
    ax.set_xticks(anios, [f"{e}\n{a}" for e, a in SERIES.values()])
    ax.set_ylabel("% de puntos en uso agrícola, pecuario o urbano")
    ax.set_ylim(0)
    ax.set_title("Transformación de los sitios de registro por zona y serie INEGI", pad=30)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncols=len(t), borderaxespad=0.3,
              handlelength=1.5, columnspacing=1.2)
    fig.savefig(destino)
    plt.close(fig)


def fig_perdida(t, estatus, destino, top=25):
    prioritarias = t[t["en_riesgo"] | t["endemica"]]
    datos = prioritarias.head(top).iloc[::-1]
    y = np.arange(len(datos))
    fig, ax = plt.subplots(figsize=(9, 0.32 * len(datos) + 1.8))
    ax.barh(y, datos["pct_a_antropico"], height=0.6, color=estilo.AZUL)
    for yi, (v, n) in enumerate(zip(datos["pct_a_antropico"],
                                    datos["puntos_naturales_serie_I"])):
        ax.annotate(f"{v:.0f} % de {n:,} puntos", (v, yi), xytext=(4, 0),
                    textcoords="offset points", va="center", fontsize=8,
                    color=estilo.TINTA_2)
    ax.set_yticks(y, [_etiqueta_especie(e, estatus) for e in datos.index], fontsize=8.5)
    ax.set_xlim(0, min(100, datos["pct_a_antropico"].max() * 1.35))
    ax.set_xlabel("% de puntos con vegetación natural en la serie I que en la VII "
                  "son uso antrópico")
    ax.grid(axis="y", visible=False)
    ax.set_title("Especies en riesgo o endémicas con más pérdida de vegetación en sus sitios\n"
                 f"(≥ {MIN_PUNTOS_ESPECIE} puntos naturales en serie I; * endémica; NOM-059/IUCN)")
    fig.savefig(destino)
    plt.close(fig)


# ─────────────────────────────────────────
# Ejecucion
# ─────────────────────────────────────────

def main(unidades):
    SALIDA.mkdir(parents=True, exist_ok=True)
    estilo.aplicar()
    csv = {"encoding": "utf-8-sig"}

    df, clases = preparar(unidades)
    clases.to_csv(SALIDA / "clases_usv.csv", index=False, **csv)
    sin_clasificar = clases[clases["condicion"].isna()]["clase_inegi"].tolist()
    estatus = estatus_especies(df)
    print(f"{len(df):,} registros de especies nativas terrestres | {len(clases)} clases INEGI"
          f" | sin clasificar: {sin_clasificar or 'ninguna'}")

    # E1
    esp = especializacion(df, estatus)
    esp.to_csv(SALIDA / "especializacion.csv", **csv)
    fig_especialistas(esp, SALIDA / "especializacion.png")
    print(f"\n[E1] {len(esp)} especies con ≥ {MIN_REGISTROS_ESPECIE} registros; "
          f"{esp['especialista'].sum()} especialistas")
    print(esp[esp["especialista"]]["formacion_principal"].value_counts().to_string())

    # E2
    tol, base = tolerancia(df, estatus)
    tol.to_csv(SALIDA / "tolerancia.csv", **csv)
    fig_tolerancia(tol, base, estatus, SALIDA / "tolerancia.png")
    print(f"\n[E2] Base: {base:.1f} % de los registros en uso antropico")
    print(tol.head(8)[["registros", "pct_antropico", "en_riesgo"]].to_string())

    # E3
    puntos = puntos_unicos(df)
    tr = transiciones(puntos)
    tr.to_csv(SALIDA / "transiciones_I_VII.csv", **csv)
    fig_transiciones(tr, SALIDA / "transiciones_I_VII.png")
    zonas = antropizacion_zonas(puntos, unidades)
    zonas.to_csv(SALIDA / "antropizacion_zonas.csv", **csv)
    fig_antropizacion(zonas, SALIDA / "antropizacion_zonas.png")
    perdida = perdida_especies(df, estatus)
    perdida.to_csv(SALIDA / "perdida_especies.csv", **csv)
    fig_perdida(perdida, estatus, SALIDA / "perdida_especies.png")

    natural_I = tr.loc[NATURAL].sum().sum()
    a_antropico = tr.loc[NATURAL, ANTROPICA].sum().sum()
    print(f"\n[E3] {len(puntos):,} puntos unicos. De {natural_I:,} con vegetacion natural en "
          f"la serie I, {a_antropico / natural_I:.1%} son uso antropico en la VII")
    print(zonas.to_string())
    print(perdida[perdida["en_riesgo"] | perdida["endemica"]].head(8)[
        ["puntos_naturales_serie_I", "pct_a_antropico", "endemica", "en_riesgo"]].to_string())
    print(f"\nSalidas en {SALIDA}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--unidades", nargs="+", default=list(ZONAS_UTM))
    main(parser.parse_args().unidades)
