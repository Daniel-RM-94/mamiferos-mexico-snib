"""Analisis comparativo entre zonas UTM (y opcionalmente paises vecinos).

Uso:
    python -m analisis.comparativo
    python -m analisis.comparativo --unidades 14a 14b 15 GUATEMALA BELICE
    python -m analisis.comparativo --incluir-marinos --incluir-exoticas

Salidas en outputs/comparativo/:
    tabla_resumen.csv                registros, riqueza, endemicas, riesgo,
                                     riqueza rarefactada, Chao1 y cobertura
    composicion_ordenes.csv / .png   % de especies de cada unidad por orden
    beta_pares.csv                   Jaccard, Sorensen y su particion en
                                     recambio / anidamiento (Baselga 2010)
    beta_jaccard.csv / .png          matriz de similitud de Jaccard
    beta_dendrograma.png             agrupamiento UPGMA sobre 1 - Jaccard
    rarefaccion.csv / .png           curvas de riqueza esperada vs registros
    especies_exclusivas.csv          especies registradas en una sola unidad
    intersecciones.csv / .png        especies por combinacion de unidades

Unidad de muestreo: un registro a nivel especie sin `dup_evento` (mismo taxon,
punto y fecha cuentan una vez). Los registros NO son individuos: la
rarefaccion estandariza por esfuerzo de registro, no por abundancia.
"""
import argparse
from itertools import combinations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import dendrogram, linkage
from scipy.spatial.distance import squareform
from scipy.special import gammaln

from analisis import estilo
from config import DIR_OUTPUTS, ZONAS_UTM
from pipeline.io import cargar_procesado

COLUMNAS = ["unidad", "especie", "ordenvalido", "generovalido", "familiavalida",
            "endemica_especie", "en_nom059", "iucn_amenazada", "es_marino", "es_exotica",
            "dup_evento",
            "clase_incertidumbre", "anio"]


# ─────────────────────────────────────────
# Datos
# ─────────────────────────────────────────

def preparar(unidades, incluir_marinos=False, incluir_exoticas=False) -> pd.DataFrame:
    df = cargar_procesado(unidades, columnas=COLUMNAS)
    if not incluir_marinos:
        df = df[~df["es_marino"]]
    if not incluir_exoticas:
        df = df[~df["es_exotica"]]
    faltantes = set(unidades) - set(df["unidad"])
    if faltantes:
        raise ValueError(f"Unidades sin registros: {sorted(faltantes)}")
    return df


def registros_especie(df: pd.DataFrame) -> pd.DataFrame:
    """Registros identificados a especie, sin duplicados de evento."""
    return df[df["especie"].notna() & ~df["dup_evento"]]


def matriz_presencia(df: pd.DataFrame, unidades) -> pd.DataFrame:
    """unidad x especie, True si la especie tiene al menos un registro."""
    pa = pd.crosstab(df["unidad"], df["especie"]) > 0
    return pa.reindex(unidades)


# ─────────────────────────────────────────
# Riqueza: rarefaccion, Chao1, cobertura
# ─────────────────────────────────────────

def riqueza_rarefactada(conteos: np.ndarray, n: int) -> float:
    """Riqueza esperada en una submuestra de n registros (Hurlbert 1971):
    E[S_n] = sum_i 1 - C(N - N_i, n) / C(N, n)."""
    conteos = np.asarray(conteos, dtype=float)
    N = conteos.sum()
    if n >= N:
        return float((conteos > 0).sum())
    resto = N - conteos
    posible = resto >= n
    log_razon = (gammaln(resto[posible] + 1) - gammaln(resto[posible] - n + 1)
                 - gammaln(N + 1) + gammaln(N - n + 1))
    prob_ausente = np.zeros_like(conteos)
    prob_ausente[posible] = np.exp(log_razon)
    return float((1 - prob_ausente).sum())


def chao1(conteos) -> float:
    """Chao1 con correccion de sesgo (Chao 2005)."""
    conteos = np.asarray(conteos)
    n, s_obs = conteos.sum(), (conteos > 0).sum()
    f1, f2 = (conteos == 1).sum(), (conteos == 2).sum()
    return s_obs + (n - 1) / n * f1 * (f1 - 1) / (2 * (f2 + 1))


def cobertura(conteos) -> float:
    """Cobertura de muestreo estimada (Chao & Jost 2012): fraccion de los
    registros de la comunidad que pertenecen a especies ya observadas."""
    conteos = np.asarray(conteos)
    n = conteos.sum()
    f1, f2 = (conteos == 1).sum(), (conteos == 2).sum()
    if f2 > 0:
        return 1 - f1 / n * ((n - 1) * f1 / ((n - 1) * f1 + 2 * f2))
    return 1 - f1 / n * ((n - 1) * (f1 - 1) / ((n - 1) * (f1 - 1) + 2))


def conteos_por_unidad(df: pd.DataFrame, unidades) -> dict:
    return {u: g.value_counts().to_numpy()
            for u, g in df.groupby("unidad")["especie"] if u in unidades}


def curvas_rarefaccion(conteos: dict, puntos=60) -> pd.DataFrame:
    filas = []
    for u, c in conteos.items():
        N = int(c.sum())
        for n in np.unique(np.r_[np.geomspace(1, N, puntos).astype(int), N]):
            filas.append((u, n, riqueza_rarefactada(c, n)))
    return pd.DataFrame(filas, columns=["unidad", "registros", "especies_esperadas"])


# ─────────────────────────────────────────
# Tablas
# ─────────────────────────────────────────

def tabla_resumen(df: pd.DataFrame) -> pd.DataFrame:
    """Resumen descriptivo por unidad (usa todos los registros, con duplicados)."""
    g = df.groupby("unidad", observed=True)
    resumen = pd.DataFrame({
        "registros": g.size(),
        "registros_sin_dup_evento": g["dup_evento"].apply(lambda s: (~s).sum()),
        "especies": g["especie"].nunique(),
        "generos": g["generovalido"].nunique(),
        "familias": g["familiavalida"].nunique(),
        "pct_marino": g["es_marino"].mean().mul(100).round(1),
        "pct_incert_<1km": g["clase_incertidumbre"].apply(
            lambda s: (s == "<1 km").mean() * 100).round(1),
        "anio_mediana": g["anio"].median(),
    })
    especies = df.dropna(subset=["especie"]).drop_duplicates(["unidad", "especie"])
    ge = especies.groupby("unidad", observed=True)
    resumen["especies_endemicas"] = ge["endemica_especie"].sum()
    resumen["especies_nom059"] = ge["en_nom059"].sum()
    resumen["especies_iucn_amenazadas"] = ge["iucn_amenazada"].sum()
    return resumen


def tabla_diversidad(conteos: dict) -> pd.DataFrame:
    n_ref = int(min(c.sum() for c in conteos.values()))
    filas = {}
    for u, c in conteos.items():
        s_chao = chao1(c)
        filas[u] = {
            "registros_analizados": int(c.sum()),
            "singletons": int((c == 1).sum()),
            "doubletons": int((c == 2).sum()),
            "n_rarefaccion": n_ref,
            "especies_rarefactadas": round(riqueza_rarefactada(c, n_ref), 1),
            "chao1": round(s_chao, 1),
            "completitud_pct": round((c > 0).sum() / s_chao * 100, 1),
            "cobertura_pct": round(cobertura(c) * 100, 2),
        }
    return pd.DataFrame.from_dict(filas, orient="index")


def composicion_ordenes(df: pd.DataFrame, unidades) -> pd.DataFrame:
    """% de las especies de cada unidad que pertenecen a cada orden."""
    especies = df.drop_duplicates(["unidad", "especie"])
    tabla = pd.crosstab(especies["ordenvalido"], especies["unidad"])[unidades]
    pct = tabla / tabla.sum() * 100
    return pct.loc[tabla.sum(axis=1).sort_values(ascending=False).index]


def beta_pares(pa: pd.DataFrame) -> pd.DataFrame:
    """Diversidad beta por pares. a = compartidas, b y c = exclusivas de cada una.
    beta_sor = beta_sim (recambio) + beta_sne (anidamiento), Baselga (2010)."""
    filas = []
    for u1, u2 in combinations(pa.index, 2):
        x, y = pa.loc[u1].to_numpy(), pa.loc[u2].to_numpy()
        a = int((x & y).sum())
        b = int((x & ~y).sum())
        c = int((~x & y).sum())
        sor = (b + c) / (2 * a + b + c)
        sim = min(b, c) / (a + min(b, c))
        filas.append({
            "unidad_1": u1, "unidad_2": u2,
            "compartidas": a, "solo_1": b, "solo_2": c,
            "jaccard_similitud": round(a / (a + b + c), 3),
            "beta_sorensen": round(sor, 3),
            "beta_recambio": round(sim, 3),
            "beta_anidamiento": round(sor - sim, 3),
        })
    return pd.DataFrame(filas)


def matriz_jaccard(pares: pd.DataFrame, unidades) -> pd.DataFrame:
    m = pd.DataFrame(1.0, index=unidades, columns=unidades)
    for f in pares.itertuples():
        m.loc[f.unidad_1, f.unidad_2] = m.loc[f.unidad_2, f.unidad_1] = f.jaccard_similitud
    return m


def especies_exclusivas(df: pd.DataFrame, pa: pd.DataFrame) -> pd.DataFrame:
    exclusivas = pa.columns[pa.sum() == 1]
    sub = df[df["especie"].isin(exclusivas)]
    return (sub.groupby(["unidad", "especie"], observed=True)
            .agg(ordenvalido=("ordenvalido", "first"),
                 familiavalida=("familiavalida", "first"),
                 registros=("especie", "size"),
                 endemica=("endemica_especie", "first"),
                 en_nom059=("en_nom059", "first"))
            .reset_index()
            .sort_values(["unidad", "registros"], ascending=[True, False]))


def intersecciones(pa: pd.DataFrame) -> pd.DataFrame:
    """Numero de especies por combinacion exacta de unidades donde aparecen."""
    combo = pa.T.apply(lambda fila: tuple(pa.index[fila.to_numpy()]), axis=1)
    conteo = combo.value_counts()
    return pd.DataFrame({"unidades": conteo.index, "especies": conteo.to_numpy(),
                         "n_unidades": [len(c) for c in conteo.index]})


# ─────────────────────────────────────────
# Figuras
# ─────────────────────────────────────────

def fig_rarefaccion(curvas, diversidad, colores, destino):
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for u, color in colores.items():
        c = curvas[curvas["unidad"] == u]
        ax.plot(c["registros"], c["especies_esperadas"], color=color, label=u)
        ax.plot(c["registros"].iloc[-1], c["especies_esperadas"].iloc[-1], "o",
                color=color, markersize=8, markeredgecolor=estilo.SUPERFICIE,
                markeredgewidth=2, zorder=3)
    n_ref = int(diversidad["n_rarefaccion"].iloc[0])
    ax.axvline(n_ref, color=estilo.TINTA_TENUE, linewidth=1)
    ax.annotate(f"n = {n_ref:,} registros\n(comparación a igual esfuerzo)",
                xy=(n_ref, 0.02), xycoords=("data", "axes fraction"),
                xytext=(6, 0), textcoords="offset points",
                color=estilo.TINTA_2, fontsize=9, va="bottom")
    ax.set_xlabel("Registros (sin duplicados de evento)")
    ax.set_ylabel("Especies esperadas")
    ax.set_title("Curvas de rarefacción por unidad")
    ax.set_xlim(0)
    ax.set_ylim(0)
    ax.xaxis.set_major_formatter(lambda x, _: f"{x:,.0f}")
    ax.legend(title="Unidad", title_fontsize=9, loc="lower right", ncols=2)
    fig.savefig(destino)
    plt.close(fig)




def fig_composicion(pct, destino):
    fig, ax = plt.subplots(figsize=(1.1 * pct.shape[1] + 3, 0.42 * pct.shape[0] + 1.5))
    im = estilo.heatmap(ax, pct.round(0), ".0f")
    ax.xaxis.tick_top()
    ax.set_title("% de especies de cada unidad por orden", pad=28)
    fig.colorbar(im, ax=ax, shrink=0.6, label="% de especies").outline.set_visible(False)
    fig.savefig(destino)
    plt.close(fig)


def fig_jaccard(m, destino):
    n = len(m)
    mascara = np.triu(np.ones((n, n), dtype=bool))  # solo triangulo inferior
    fig, ax = plt.subplots(figsize=(0.8 * n + 3, 0.7 * n + 1.5))
    im = estilo.heatmap(ax, m.iloc[1:, :-1], ".2f", vmax=1,
                  mascara=mascara[1:, :-1])
    ax.set_title("Similitud de Jaccard (especies compartidas / total del par)")
    fig.colorbar(im, ax=ax, shrink=0.6, label="Jaccard").outline.set_visible(False)
    fig.savefig(destino)
    plt.close(fig)


def fig_dendrograma(m, destino):
    distancia = squareform(1 - m.to_numpy(), checks=False)
    fig, ax = plt.subplots(figsize=(8, 0.45 * len(m) + 1.5))
    dendrogram(linkage(distancia, method="average"), labels=list(m.index),
               orientation="right", ax=ax, color_threshold=0,
               above_threshold_color=estilo.TINTA_2)
    ax.set_xlabel("Distancia (1 - Jaccard)")
    ax.set_title("Agrupamiento de unidades por composición de especies (UPGMA)")
    ax.grid(axis="y", visible=False)
    ax.spines["left"].set_visible(False)
    fig.savefig(destino)
    plt.close(fig)


def fig_intersecciones(inter, unidades, destino, top=15):
    datos = inter.head(top).reset_index(drop=True)
    x = np.arange(len(datos))
    fig, (ax_b, ax_m) = plt.subplots(
        2, 1, figsize=(0.55 * len(datos) + 3, 6), sharex=True,
        gridspec_kw={"height_ratios": [2.2, 1.3], "hspace": 0.05})

    ax_b.bar(x, datos["especies"], width=0.6, color=estilo.AZUL)
    for xi, v in zip(x, datos["especies"]):
        ax_b.annotate(f"{v}", (xi, v), xytext=(0, 3), textcoords="offset points",
                      ha="center", fontsize=8.5, color=estilo.TINTA_2)
    ax_b.set_ylabel("Especies")
    ax_b.set_title(f"Especies por combinación de unidades ({top} más frecuentes)")
    ax_b.grid(axis="x", visible=False)

    filas = {u: i for i, u in enumerate(unidades[::-1])}
    for xi, combo in zip(x, datos["unidades"]):
        ax_m.scatter([xi] * len(unidades), range(len(unidades)), s=40,
                     color=estilo.REJILLA, zorder=1)
        ys = sorted(filas[u] for u in combo)
        ax_m.plot([xi, xi], [ys[0], ys[-1]], color=estilo.TINTA, linewidth=2, zorder=2)
        ax_m.scatter([xi] * len(ys), ys, s=40, color=estilo.TINTA, zorder=3)
    ax_m.set_yticks(range(len(unidades)), unidades[::-1])
    ax_m.set_xticks([])
    ax_m.grid(False)
    for s in ax_m.spines.values():
        s.set_visible(False)
    ax_m.tick_params(length=0)
    fig.savefig(destino)
    plt.close(fig)


# ─────────────────────────────────────────
# Ejecucion
# ─────────────────────────────────────────

def main(unidades, incluir_marinos=False, incluir_exoticas=False):
    salida = DIR_OUTPUTS / "comparativo"
    salida.mkdir(parents=True, exist_ok=True)
    estilo.aplicar()
    colores = estilo.colores_unidades(unidades)
    csv = {"encoding": "utf-8-sig"}

    df = preparar(unidades, incluir_marinos, incluir_exoticas)
    registros = registros_especie(df)
    pa = matriz_presencia(registros, unidades)
    conteos = conteos_por_unidad(registros, unidades)
    print(f"{len(df):,} registros | {len(registros):,} a especie sin dup_evento | "
          f"{pa.shape[1]} especies | marinos {'incluidos' if incluir_marinos else 'excluidos'} | "
          f"exoticas {'incluidas' if incluir_exoticas else 'excluidas'}")

    # Riqueza
    diversidad = tabla_diversidad(conteos)
    resumen = tabla_resumen(df).join(diversidad).loc[unidades]
    resumen.to_csv(salida / "tabla_resumen.csv", **csv)
    curvas = curvas_rarefaccion(conteos)
    curvas.to_csv(salida / "rarefaccion.csv", index=False, **csv)
    fig_rarefaccion(curvas, diversidad, colores, salida / "rarefaccion.png")

    # Composicion
    pct = composicion_ordenes(registros, unidades)
    pct.round(2).to_csv(salida / "composicion_ordenes.csv", **csv)
    fig_composicion(pct, salida / "composicion_ordenes.png")

    # Diversidad beta
    pares = beta_pares(pa)
    pares.to_csv(salida / "beta_pares.csv", index=False, **csv)
    m = matriz_jaccard(pares, unidades)
    m.to_csv(salida / "beta_jaccard.csv", **csv)
    fig_jaccard(m, salida / "beta_jaccard.png")
    fig_dendrograma(m, salida / "beta_dendrograma.png")

    # Exclusivas y compartidas
    especies_exclusivas(registros, pa).to_csv(salida / "especies_exclusivas.csv",
                                              index=False, **csv)
    inter = intersecciones(pa)
    inter.assign(unidades=inter["unidades"].map(" + ".join)).to_csv(
        salida / "intersecciones.csv", index=False, **csv)
    fig_intersecciones(inter, unidades, salida / "intersecciones.png")

    pd.set_option("display.width", 200)
    print("\nRiqueza por unidad:")
    print(resumen[["registros_analizados", "especies", "especies_rarefactadas",
                   "chao1", "completitud_pct", "cobertura_pct"]].to_string())
    print("\nPares mas similares (Jaccard):")
    print(pares.nlargest(5, "jaccard_similitud")[
        ["unidad_1", "unidad_2", "compartidas", "jaccard_similitud",
         "beta_recambio", "beta_anidamiento"]].to_string(index=False))
    print(f"\nSalidas en {salida}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--unidades", nargs="+", default=list(ZONAS_UTM),
                        help="zonas UTM y/o paises (valor de paismapa); "
                             "por defecto las 7 zonas de Mexico")
    parser.add_argument("--incluir-marinos", action="store_true",
                        help="incluye cetaceos, sirenios y pinnipedos")
    parser.add_argument("--incluir-exoticas", action="store_true",
                        help="incluye especies exoticas e introducidas")
    args = parser.parse_args()
    main(args.unidades, args.incluir_marinos, args.incluir_exoticas)
