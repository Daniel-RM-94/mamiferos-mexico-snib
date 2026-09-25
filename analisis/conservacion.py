"""Conservacion: listas de riesgo, cobertura por ANP, exoticas y especies sin
registros recientes (zonas UTM de Mexico).

Uso:
    python -m analisis.conservacion
    python -m analisis.conservacion --excluir-marinos

Salidas en outputs/conservacion/:
    especies.csv                 ficha por especie nativa: categorias de riesgo,
                                 registros, zonas, % en ANP, primer y ultimo ano
    cruce_nom_iucn.csv / .png    especies por categoria NOM-059 x IUCN (C1)
    discrepancias_nom_iucn.csv   amenazadas en una lista y no en la otra (C1)
    anp_por_zona.csv / .png      % de registros dentro de ANP por zona (C3)
    vacios_anp.csv / .png        especies en riesgo con poca cobertura de ANP (C3)
    exoticas.csv / .png          especies exoticas: extension y registros por decada (C4)
    sin_registro_reciente.csv    especies sin registros desde ANIO_RECIENTE (D2)
    sin_registro_reciente_zonas.csv / .png   lo mismo por zona

Categorias de riesgo: la NOM-059 y la IUCN a veces listan una subespecie y no la
especie completa (p. ej. subespecies insulares de Chaetodipus spinatus). Por eso
cada especie lleva dos columnas: `*_especie` (categoria de los registros sin
subespecie) y `*_max` (la mas alta entre la especie y sus subespecies).
Los analisis por registro (ANP, por zona) usan la categoria del propio registro.

Las ausencias de registro no son ausencias de la especie: sin registro
reciente puede significar declive, pero tambien falta de muestreo.
"""
import argparse

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analisis import estilo
from config import ANIO_RECIENTE, DIR_OUTPUTS, ESPECIES_INTRODUCIDAS, ZONAS_UTM
from pipeline.io import cargar_procesado
from pipeline.limpieza import CATEGORIAS_CITES, CATEGORIAS_IUCN, CATEGORIAS_NOM, valor_nivel_especie

SALIDA = DIR_OUTPUTS / "conservacion"
IUCN_AMENAZADA = ["VU", "EN", "CR", "EW"]
MIN_REGISTROS_VACIO = 20      # especies en riesgo con al menos estos registros...
MAX_PCT_ANP_VACIO = 10        # ...y como maximo este % dentro de ANP = vacio
COLUMNAS = ["unidad", "especie", "subespecie", "ordenvalido", "familiavalida",
            "nombrecomun", "endemica_especie", "nom059_cod", "iucn_cod", "cites_cod",
            "en_nom059", "iucn_amenazada", "exoticainvasora", "es_marino", "es_exotica",
            "dup_evento", "dentro_anp", "anp_nombre", "anio", "celda_id",
            "tipo_registro"]


# ─────────────────────────────────────────
# Datos
# ─────────────────────────────────────────

def preparar(unidades, incluir_marinos=True) -> pd.DataFrame:
    """Registros a nivel especie, sin duplicados de evento."""
    df = cargar_procesado(unidades, columnas=COLUMNAS)
    df = df[df["especie"].notna() & ~df["dup_evento"]]
    if not incluir_marinos:
        df = df[~df["es_marino"]]
    df["en_riesgo"] = df["en_nom059"] | df["iucn_amenazada"]
    return df


def _categoria_especie(df, col, categorias):
    valores = valor_nivel_especie(df, col).reindex(sorted(df["especie"].unique()))
    return pd.Categorical(valores, categories=categorias, ordered=True)


def tabla_especies(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("especie")
    t = pd.DataFrame({
        "orden": g["ordenvalido"].first(),
        "familia": g["familiavalida"].first(),
        "nombre_comun": g["nombrecomun"].agg(
            lambda s: s.dropna().iat[0].split(",")[0].strip() if s.notna().any() else ""),
        "endemica": g["endemica_especie"].first(),
        "es_marino": g["es_marino"].any(),
        "es_exotica": g["es_exotica"].any(),
    })
    for col, cats, nombre in [("nom059_cod", CATEGORIAS_NOM, "nom059"),
                              ("iucn_cod", CATEGORIAS_IUCN, "iucn"),
                              ("cites_cod", CATEGORIAS_CITES, "cites")]:
        t[f"{nombre}_especie"] = _categoria_especie(df, col, cats)
        t[f"{nombre}_max"] = g[col].max()
    t["riesgo_especie"] = t["nom059_especie"].notna() | t["iucn_especie"].isin(IUCN_AMENAZADA)
    t["riesgo_alguna_subespecie"] = (t["nom059_max"].notna()
                                     | t["iucn_max"].isin(IUCN_AMENAZADA))
    t["riesgo_solo_subespecies"] = t["riesgo_alguna_subespecie"] & ~t["riesgo_especie"]

    t["registros"] = g.size()
    t["registros_en_riesgo"] = g["en_riesgo"].sum()
    t["zonas"] = g["unidad"].agg(lambda s: " ".join(u for u in ZONAS_UTM if u in set(s)))
    t["n_zonas"] = g["unidad"].nunique()
    t["celdas"] = g["celda_id"].nunique()
    t["pct_dentro_anp"] = g["dentro_anp"].mean().mul(100).round(1)
    t["anp_principal"] = g["anp_nombre"].agg(
        lambda s: s.mode().iat[0] if s.notna().any() else "")
    t["primer_anio"] = g["anio"].min()
    t["ultimo_anio"] = g["anio"].max()
    t["registros_recientes"] = g["anio"].agg(lambda a: int((a >= ANIO_RECIENTE).sum()))
    return t


# ─────────────────────────────────────────
# C1. NOM-059 x IUCN
# ─────────────────────────────────────────

def cruce_nom_iucn(esp: pd.DataFrame) -> pd.DataFrame:
    nom = esp["nom059_especie"].cat.add_categories("Sin categoría").fillna("Sin categoría")
    nom = nom.cat.reorder_categories(["Sin categoría"] + CATEGORIAS_NOM)
    iucn = esp["iucn_especie"].cat.add_categories("No evaluada").fillna("No evaluada")
    return pd.crosstab(nom, iucn, dropna=False).rename_axis(
        index="NOM-059", columns="IUCN")


def discrepancias(esp: pd.DataFrame) -> pd.DataFrame:
    sin_nom = esp["nom059_especie"].isna() & esp["iucn_especie"].isin(IUCN_AMENAZADA)
    nom_alta_iucn_lc = esp["nom059_especie"].isin(["P", "E"]) & (esp["iucn_especie"] == "LC")
    nom_sin_iucn = esp["nom059_especie"].notna() & esp["iucn_especie"].isna()
    motivo = np.select(
        [sin_nom, nom_alta_iucn_lc, nom_sin_iucn],
        ["Amenazada en IUCN, fuera de NOM-059",
         "En peligro/extinta en NOM-059, LC en IUCN",
         "En NOM-059, sin evaluacion IUCN"], default="")
    cols = ["nombre_comun", "orden", "familia", "endemica", "nom059_especie",
            "iucn_especie", "registros", "zonas", "ultimo_anio"]
    return (esp.assign(motivo=motivo)[motivo != ""][["motivo"] + cols]
            .sort_values(["motivo", "registros"], ascending=[True, False]))


def fig_cruce(cruce, destino):
    fig, ax = plt.subplots(figsize=(9, 4.2))
    im = estilo.heatmap(ax, cruce, "d")
    ax.set_xlabel("IUCN")
    ax.set_ylabel("NOM-059")
    ax.set_title("Especies nativas por categoría de riesgo: NOM-059 × IUCN")
    fig.colorbar(im, ax=ax, shrink=0.8, label="Especies").outline.set_visible(False)
    fig.savefig(destino)
    plt.close(fig)


# ─────────────────────────────────────────
# C3. Cobertura de ANP
# ─────────────────────────────────────────

def anp_por_zona(df: pd.DataFrame, unidades) -> pd.DataFrame:
    g = df.groupby("unidad")
    t = pd.DataFrame({
        "registros": g.size(),
        "pct_todos_en_anp": g["dentro_anp"].mean().mul(100),
        "registros_en_riesgo": g["en_riesgo"].sum(),
        "pct_en_riesgo_en_anp": df[df["en_riesgo"]].groupby("unidad")["dentro_anp"]
                                .mean().mul(100),
        "especies_en_riesgo": df[df["en_riesgo"]].groupby("unidad")["especie"].nunique(),
    }).reindex(unidades)
    sin_anp = (df[df["en_riesgo"]].groupby(["unidad", "especie"])["dentro_anp"].any()
               .groupby("unidad").agg(lambda s: int((~s).sum())))
    t["especies_en_riesgo_nunca_en_anp"] = sin_anp
    return t.round(1)


def vacios_anp(esp: pd.DataFrame) -> pd.DataFrame:
    en_riesgo = esp[esp["riesgo_alguna_subespecie"]]
    vacio = ((en_riesgo["registros"] >= MIN_REGISTROS_VACIO)
             & (en_riesgo["pct_dentro_anp"] <= MAX_PCT_ANP_VACIO))
    cols = ["nombre_comun", "orden", "endemica", "nom059_max", "iucn_max",
            "riesgo_solo_subespecies", "registros", "pct_dentro_anp", "anp_principal",
            "zonas", "celdas"]
    return en_riesgo.loc[vacio, cols].sort_values(["pct_dentro_anp", "registros"],
                                                  ascending=[True, False])


def fig_anp_zonas(t, destino):
    y = np.arange(len(t))[::-1]
    alto = 0.36
    fig, ax = plt.subplots(figsize=(8.5, 0.62 * len(t) + 1.6))
    series = [("pct_todos_en_anp", "Todos los registros", estilo.CATEGORICA[0]),
              ("pct_en_riesgo_en_anp", "Registros de especies en riesgo", estilo.CATEGORICA[1])]
    for k, (col, etiqueta, color) in enumerate(series):
        pos = y + alto / 2 - k * alto
        ax.barh(pos, t[col], height=alto - 0.04, color=color, label=etiqueta)
        for p, v in zip(pos, t[col]):
            ax.annotate(f"{v:.0f} %", (v, p), xytext=(4, 0), textcoords="offset points",
                        va="center", fontsize=8.5, color=estilo.TINTA_2)
    ax.set_yticks(y, t.index)
    ax.set_xlabel("% de registros dentro de un ANP")
    ax.set_xlim(0, max(t[[c for c, *_ in series]].max()) * 1.15)
    ax.grid(axis="y", visible=False)
    ax.set_title("Registros dentro de Áreas Naturales Protegidas por zona", pad=30)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncols=2, borderaxespad=0.3)
    fig.savefig(destino)
    plt.close(fig)


def fig_vacios(vacios, destino, top=25):
    datos = vacios.sort_values("registros", ascending=False).head(top)
    datos = datos.sort_values("pct_dentro_anp", ascending=False)
    etiquetas = [f"{estilo.cursiva(e)}  ({'/'.join(str(v) for v in (n, i) if pd.notna(v))})"
                 for e, n, i in zip(datos.index, datos["nom059_max"], datos["iucn_max"])]
    fig, ax = plt.subplots(figsize=(9, 0.32 * len(datos) + 1.6))
    y = np.arange(len(datos))
    ax.barh(y, datos["pct_dentro_anp"], height=0.6, color=estilo.AZUL)
    for yi, (pct, n) in enumerate(zip(datos["pct_dentro_anp"], datos["registros"])):
        ax.annotate(f"{pct:.0f} % de {n:,} reg.", (pct, yi), xytext=(4, 0),
                    textcoords="offset points", va="center", fontsize=8, color=estilo.TINTA_2)
    ax.set_yticks(y, etiquetas, fontsize=8.5)
    ax.set_xlim(0, MAX_PCT_ANP_VACIO * 1.6)
    ax.set_xlabel("% de registros dentro de un ANP")
    ax.grid(axis="y", visible=False)
    ax.set_title(f"Especies en riesgo con ≤ {MAX_PCT_ANP_VACIO} % de registros en ANP\n"
                 f"(las {len(datos)} con más registros; entre paréntesis, NOM-059 / IUCN)")
    fig.savefig(destino)
    plt.close(fig)


# ─────────────────────────────────────────
# C4. Exoticas
# ─────────────────────────────────────────

def tabla_exoticas(unidades) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = cargar_procesado(unidades, columnas=COLUMNAS)
    df = df[df["es_exotica"] & df["especie"].notna() & ~df["dup_evento"]]
    g = df.groupby("especie")
    t = pd.DataFrame({
        "nombre_comun": g["nombrecomun"].agg(
            lambda s: s.dropna().iat[0].split(",")[0].strip() if s.notna().any() else ""),
        "marca_snib": g["exoticainvasora"].agg(
            lambda s: s.dropna().mode().iat[0] if s.notna().any() else ""),
        "registros": g.size(),
        "zonas": g["unidad"].agg(lambda s: " ".join(u for u in ZONAS_UTM if u in set(s))),
        "celdas": g["celda_id"].nunique(),
        "primer_anio": g["anio"].min(),
        "ultimo_anio": g["anio"].max(),
        "pct_recientes": g["anio"].agg(
            lambda a: (a.dropna() >= ANIO_RECIENTE).mean() * 100).round(1),
        "pct_dentro_anp": g["dentro_anp"].mean().mul(100).round(1),
    })
    t.loc[t.index.isin(ESPECIES_INTRODUCIDAS), "marca_snib"] = "lista manual (config)"
    t = t.sort_values("registros", ascending=False)

    decada = pd.cut(df["anio"].astype(float), [1749, 1949, 1959, 1969, 1979, 1989,
                                               1999, 2009, 2019, 2029],
                    labels=["<1950", "1950s", "1960s", "1970s", "1980s", "1990s",
                            "2000s", "2010s", "2020s"])
    por_decada = pd.crosstab(df["especie"], decada).reindex(t.index)
    return t, por_decada


def fig_exoticas(t, por_decada, destino, min_registros=10):
    datos = por_decada[t["registros"] >= min_registros]
    etiquetas = [f"{estilo.cursiva(e)} ({t.at[e, 'nombre_comun']})" if t.at[e, "nombre_comun"]
                 else estilo.cursiva(e)
                 for e in datos.index]
    fig, ax = plt.subplots(figsize=(10, 0.36 * len(datos) + 1.8))
    im = estilo.heatmap(ax, datos.set_axis(etiquetas), "d")
    ax.xaxis.tick_top()
    ax.set_title("Registros de especies exóticas por década "
                 f"(especies con ≥ {min_registros} registros)", pad=26)
    fig.colorbar(im, ax=ax, shrink=0.6, label="Registros").outline.set_visible(False)
    fig.savefig(destino)
    plt.close(fig)


# ─────────────────────────────────────────
# D2. Sin registros recientes
# ─────────────────────────────────────────

def sin_registro_reciente(esp: pd.DataFrame) -> pd.DataFrame:
    cols = ["nombre_comun", "orden", "familia", "endemica", "nom059_max", "iucn_max",
            "registros", "zonas", "primer_anio", "ultimo_anio"]
    viejas = esp[esp["ultimo_anio"] < ANIO_RECIENTE]
    return viejas[cols].sort_values(["ultimo_anio", "registros"])


def sin_registro_reciente_zonas(df: pd.DataFrame, esp: pd.DataFrame, unidades):
    """Por zona: especies con registros fechados en la zona, pero ninguno desde
    ANIO_RECIENTE. Se distingue si tampoco hay registros recientes en el resto."""
    fechados = df[df["anio"].notna()]
    ultimo = fechados.groupby(["unidad", "especie"])["anio"].max().reset_index()
    viejas = ultimo[ultimo["anio"] < ANIO_RECIENTE].copy()
    reciente = (esp["ultimo_anio"] >= ANIO_RECIENTE).fillna(False).astype(bool)
    viejas["reciente_en_mexico"] = viejas["especie"].map(reciente).astype(bool)
    viejas["en_riesgo"] = viejas["especie"].map(esp["riesgo_alguna_subespecie"]).astype(bool)
    viejas["endemica"] = viejas["especie"].map(esp["endemica"])
    resumen = pd.DataFrame({
        "sin_registro_reciente_en_mexico": viejas[~viejas["reciente_en_mexico"]]
                                           .groupby("unidad").size(),
        "solo_sin_registro_reciente_en_la_zona": viejas[viejas["reciente_en_mexico"]]
                                                 .groupby("unidad").size(),
        "de_ellas_en_riesgo": viejas[viejas["en_riesgo"]].groupby("unidad").size(),
        "especies_con_registros_en_la_zona": fechados.groupby("unidad")["especie"].nunique(),
    }).reindex(unidades).fillna(0).astype(int)
    return viejas.rename(columns={"anio": "ultimo_anio_en_zona"}), resumen


def fig_sin_reciente(resumen, destino):
    y = np.arange(len(resumen))[::-1]
    a = resumen["sin_registro_reciente_en_mexico"]
    b = resumen["solo_sin_registro_reciente_en_la_zona"]
    fig, ax = plt.subplots(figsize=(8.5, 0.55 * len(resumen) + 1.6))
    ax.barh(y, a, height=0.6, color=estilo.CATEGORICA[0],
            label=f"Sin registros desde {ANIO_RECIENTE} en todo Mexico")
    ax.barh(y, b, left=a, height=0.6, color=estilo.CATEGORICA[1],
            edgecolor=estilo.SUPERFICIE, linewidth=2,
            label=f"Sin registros desde {ANIO_RECIENTE} en la zona (si en otras)")
    for yi, total in zip(y, a + b):
        ax.annotate(f"{total}", (total, yi), xytext=(4, 0), textcoords="offset points",
                    va="center", fontsize=8.5, color=estilo.TINTA_2)
    ax.set_yticks(y, resumen.index)
    ax.set_xlabel("Especies")
    ax.grid(axis="y", visible=False)
    ax.set_title(f"Especies registradas en la zona sin registros desde {ANIO_RECIENTE}",
                 pad=30)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncols=2, borderaxespad=0.3)
    fig.savefig(destino)
    plt.close(fig)


# ─────────────────────────────────────────
# Ejecucion
# ─────────────────────────────────────────

def main(unidades, incluir_marinos=True):
    SALIDA.mkdir(parents=True, exist_ok=True)
    estilo.aplicar()
    csv = {"encoding": "utf-8-sig"}

    todos = preparar(unidades, incluir_marinos)
    df = todos[~todos["es_exotica"]]
    esp = tabla_especies(df)
    esp.to_csv(SALIDA / "especies.csv", **csv)
    print(f"{len(esp)} especies nativas | {len(df):,} registros sin dup_evento | "
          f"en riesgo: {esp['riesgo_especie'].sum()} a nivel especie, "
          f"{esp['riesgo_solo_subespecies'].sum()} mas solo por subespecies")

    # C1
    cruce = cruce_nom_iucn(esp)
    cruce.to_csv(SALIDA / "cruce_nom_iucn.csv", **csv)
    fig_cruce(cruce, SALIDA / "cruce_nom_iucn.png")
    disc = discrepancias(esp)
    disc.to_csv(SALIDA / "discrepancias_nom_iucn.csv", **csv)
    print("\n[C1] Discrepancias NOM-059 / IUCN:")
    print(disc["motivo"].value_counts().to_string())

    # C3
    zonas = anp_por_zona(df, unidades)
    zonas.to_csv(SALIDA / "anp_por_zona.csv", **csv)
    fig_anp_zonas(zonas, SALIDA / "anp_por_zona.png")
    vacios = vacios_anp(esp)
    vacios.to_csv(SALIDA / "vacios_anp.csv", **csv)
    fig_vacios(vacios, SALIDA / "vacios_anp.png")
    print("\n[C3] % de registros dentro de ANP:")
    print(zonas[["pct_todos_en_anp", "pct_en_riesgo_en_anp",
                 "especies_en_riesgo", "especies_en_riesgo_nunca_en_anp"]].to_string())
    print(f"    Vacios: {len(vacios)} especies en riesgo con ≥ {MIN_REGISTROS_VACIO} "
          f"registros y ≤ {MAX_PCT_ANP_VACIO} % en ANP")

    # C4
    exo, exo_decadas = tabla_exoticas(unidades)
    exo.join(exo_decadas).to_csv(SALIDA / "exoticas.csv", **csv)
    fig_exoticas(exo, exo_decadas, SALIDA / "exoticas.png")
    print(f"\n[C4] {len(exo)} especies exoticas, {exo['registros'].sum():,} registros")
    print(exo.head(8)[["nombre_comun", "registros", "zonas", "pct_recientes"]].to_string())

    # D2
    sin_reciente = sin_registro_reciente(esp)
    sin_reciente.to_csv(SALIDA / "sin_registro_reciente.csv", **csv)
    detalle, resumen = sin_registro_reciente_zonas(df, esp, unidades)
    detalle.to_csv(SALIDA / "sin_registro_reciente_zonas.csv", index=False, **csv)
    fig_sin_reciente(resumen, SALIDA / "sin_registro_reciente_zonas.png")
    print(f"\n[D2] {len(sin_reciente)} especies sin registros desde {ANIO_RECIENTE} "
          f"({sin_reciente['nom059_max'].notna().sum()} en NOM-059)")
    print(resumen.to_string())
    print(f"\nSalidas en {SALIDA}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--unidades", nargs="+", default=list(ZONAS_UTM))
    parser.add_argument("--excluir-marinos", action="store_true",
                        help="excluye cetaceos, sirenios y pinnipedos")
    args = parser.parse_args()
    main(args.unidades, not args.excluir_marinos)
