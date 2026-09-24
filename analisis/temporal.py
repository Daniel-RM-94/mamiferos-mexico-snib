"""Analisis temporal: como se construyo el conocimiento y estacionalidad.

Uso:
    python -m analisis.temporal
    python -m analisis.temporal --especies "Myotis velifer" "Lasiurus borealis"

Salidas en outputs/temporal/:
    registros_decada_tipo.csv / .png   D1: registros por decada y tipo de registro
    esfuerzo_zona_decada.csv / .png    D1: registros por zona y decada
    acumulacion_especies.csv / .png    D1: especies acumuladas por ano en cada zona
    saturacion_zonas.csv               ano en que cada zona alcanzo 50/90 % de sus
                                       especies y especies agregadas desde ANIO_RECIENTE
    especies_nuevas_zona.csv           primer registro de cada especie en cada zona
    estacionalidad.csv / .png          D3: indice mensual corregido por esfuerzo

Indice de estacionalidad (D3): para cada mes y banda de latitud,
    (registros de la especie / registros de todos los murcielagos) en el mes
    ------------------------------------------------------------------------
    (registros de la especie / registros de todos los murcielagos) en el ano
con ventana movil circular de 3 meses. 1 = lo esperado por el esfuerzo del mes;
>1 = la especie esta sobrerrepresentada ese mes (presente o mas activa).
"""
import argparse

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analisis import estilo
from config import ANIO_RECIENTE, ANIO_VALIDO, DIR_OUTPUTS, ZONAS_UTM
from pipeline.io import cargar_procesado

SALIDA = DIR_OUTPUTS / "temporal"
MURCIELAGOS_MIGRATORIOS = [
    "Leptonycteris yerbabuenae", "Leptonycteris nivalis", "Choeronycteris mexicana",
    "Tadarida brasiliensis", "Lasiurus cinereus", "Lasiurus frantzii",
]
LATITUD_NORTE = 24             # divide las bandas norte / sur de la estacionalidad
MIN_REGISTROS_BANDA = 30       # registros con mes para graficar una banda
TIPOS = ["Coleccion", "Observacion humana", "Observacion automatica", "Otro/desconocido"]
ETIQUETAS_TIPO = {"Coleccion": "Colección científica", "Observacion humana": "Observación humana",
                  "Observacion automatica": "Fototrampeo / acústica",
                  "Otro/desconocido": "Otro o desconocido"}
MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
COLUMNAS = ["unidad", "especie", "ordenvalido", "anio", "mes", "latitud", "tipo_registro",
            "dup_evento", "es_marino", "es_exotica"]


def preparar(unidades) -> pd.DataFrame:
    df = cargar_procesado(unidades, columnas=COLUMNAS)
    return df[df["especie"].notna() & ~df["dup_evento"] & ~df["es_exotica"]
              & ~df["es_marino"]].copy()


def _decada(anio):
    etiquetas = ["<1900"] + [f"{d}s" for d in range(1900, 2030, 10)]
    cortes = [ANIO_VALIDO[0] - 1] + list(range(1899, 2030, 10))
    return pd.cut(anio.astype(float), cortes, labels=etiquetas)


# ─────────────────────────────────────────
# D1. Registros en el tiempo
# ─────────────────────────────────────────

def registros_decada_tipo(df):
    return (pd.crosstab(_decada(df["anio"]), df["tipo_registro"])
            .reindex(columns=TIPOS, fill_value=0))


def esfuerzo_zona_decada(df, unidades):
    return pd.crosstab(df["unidad"], _decada(df["anio"])).reindex(unidades)


def acumulacion_especies(df, unidades):
    """Especies acumuladas por ano: una especie cuenta desde su primer registro
    fechado en la zona."""
    primeros = (df[df["anio"].notna()].groupby(["unidad", "especie"])["anio"].min()
                .astype(int).rename("primer_anio").reset_index())
    anios = np.arange(1850, ANIO_VALIDO[1] + 1)
    curvas = {u: (primeros[primeros["unidad"] == u]["primer_anio"].value_counts()
                  .reindex(anios, fill_value=0).cumsum()) for u in unidades}
    return pd.DataFrame(curvas), primeros


def saturacion(curvas: pd.DataFrame, primeros: pd.DataFrame) -> pd.DataFrame:
    total = curvas.iloc[-1]
    filas = {}
    for u in curvas:
        c = curvas[u]
        filas[u] = {
            "especies": int(total[u]),
            "anio_50pct": int(c[c >= 0.5 * total[u]].index[0]),
            "anio_90pct": int(c[c >= 0.9 * total[u]].index[0]),
            f"agregadas_desde_{ANIO_RECIENTE}": int(
                (primeros[(primeros["unidad"] == u)]["primer_anio"] >= ANIO_RECIENTE).sum()),
        }
    t = pd.DataFrame.from_dict(filas, orient="index")
    t[f"pct_agregadas_desde_{ANIO_RECIENTE}"] = (
        t[f"agregadas_desde_{ANIO_RECIENTE}"] / t["especies"] * 100).round(1)
    return t


def fig_decada_tipo(t, destino):
    colores = dict(zip(TIPOS, estilo.CATEGORICA[:3] + [estilo.OTROS]))
    x = np.arange(len(t))
    fig, ax = plt.subplots(figsize=(10, 5))
    abajo = np.zeros(len(t))
    for tipo in TIPOS:
        ax.bar(x, t[tipo], bottom=abajo, width=0.7, color=colores[tipo],
               edgecolor=estilo.SUPERFICIE, linewidth=1.5, label=ETIQUETAS_TIPO[tipo])
        abajo += t[tipo].to_numpy()
    for xi, total in zip(x, abajo):
        ax.annotate(f"{total / 1000:.0f}k" if total >= 1000 else f"{total:.0f}",
                    (xi, total), xytext=(0, 3), textcoords="offset points",
                    ha="center", fontsize=8.5, color=estilo.TINTA_2)
    etiquetas = [e if e != "2020s" else f"2020–{str(ANIO_VALIDO[1])[2:]}" for e in t.index]
    ax.set_xticks(x, etiquetas)
    ax.set_ylim(0, abajo.max() * 1.08)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
    ax.set_ylabel("Registros (sin duplicados de evento)")
    ax.grid(axis="x", visible=False)
    ax.set_title("Registros por década y tipo de registro", pad=30)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncols=4, borderaxespad=0.3)
    fig.savefig(destino)
    plt.close(fig)


def fig_esfuerzo(t, destino):
    t = t.loc[:, t.columns != "<1900"]
    fig, ax = plt.subplots(figsize=(12, 0.5 * len(t) + 1.8))
    im = estilo.heatmap(ax, t / 1000, ".1f")
    ax.set_xticks(range(t.shape[1]), [c[:-1] + "s" if c != "2020s" else "2020–" for c in t.columns])
    ax.xaxis.tick_top()
    ax.set_title("Registros por zona y década (miles; sin duplicados de evento)", pad=28)
    fig.colorbar(im, ax=ax, shrink=0.8, label="Miles de registros").outline.set_visible(False)
    fig.savefig(destino)
    plt.close(fig)


def fig_acumulacion(curvas, destino):
    colores = estilo.colores_unidades(list(curvas.columns))
    datos = curvas.loc[1880:]
    fig, ax = plt.subplots(figsize=(9, 5.4))
    for u in datos:
        ax.plot(datos.index, datos[u], color=colores[u], label=u)
    ax.axvline(ANIO_RECIENTE, color=estilo.TINTA_TENUE, linewidth=1)
    ax.set_xlim(1880, ANIO_VALIDO[1])
    ax.set_ylim(0)
    ax.set_xlabel("Año")
    ax.set_ylabel("Especies con al menos un registro")
    ax.set_title("Acumulación de especies registradas por zona", pad=30)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncols=len(datos.columns),
              borderaxespad=0.3, handlelength=1.5, columnspacing=1.2)
    fig.savefig(destino)
    plt.close(fig)


# ─────────────────────────────────────────
# D3. Estacionalidad
# ─────────────────────────────────────────

def _suma_movil_circular(serie):
    return serie + serie.shift(1).fillna(serie.iloc[-1]) + serie.shift(-1).fillna(serie.iloc[0])


def estacionalidad(df, especies, orden="Chiroptera"):
    grupo = df[(df["ordenvalido"] == orden) & df["mes"].notna()].copy()
    grupo["banda"] = np.where(grupo["latitud"] >= LATITUD_NORTE,
                              f"Norte (≥ {LATITUD_NORTE}°)", f"Sur (< {LATITUD_NORTE}°)")
    filas = []
    for banda, sub in grupo.groupby("banda"):
        total_mes = sub["mes"].astype(int).value_counts().reindex(range(1, 13), fill_value=0)
        for esp in especies:
            mes_esp = (sub.loc[sub["especie"] == esp, "mes"].astype(int).value_counts()
                       .reindex(range(1, 13), fill_value=0))
            n = int(mes_esp.sum())
            if n == 0:
                continue
            proporcion = _suma_movil_circular(mes_esp) / _suma_movil_circular(total_mes)
            indice = proporcion / (n / total_mes.sum())
            for m in range(1, 13):
                filas.append({"especie": esp, "banda": banda, "mes": m,
                              "registros": int(mes_esp[m]), "registros_banda": n,
                              "indice": round(float(indice[m]), 3)})
    return pd.DataFrame(filas)


def fig_estacionalidad(est, especies, destino):
    bandas = sorted(est["banda"].unique())
    colores = dict(zip(bandas, estilo.CATEGORICA[:2]))
    columnas = 3
    filas = int(np.ceil(len(especies) / columnas))
    fig, ejes = plt.subplots(filas, columnas, figsize=(4.4 * columnas, 3.1 * filas),
                             sharex=True, sharey=True, squeeze=False)
    tope = est.loc[est["registros_banda"] >= MIN_REGISTROS_BANDA, "indice"].max()
    for ax, esp in zip(ejes.flat, especies):
        ax.axhline(1, color=estilo.TINTA_TENUE, linewidth=1)
        for banda in bandas:
            d = est[(est["especie"] == esp) & (est["banda"] == banda)]
            if d.empty or d["registros_banda"].iat[0] < MIN_REGISTROS_BANDA:
                continue
            ax.plot(d["mes"], d["indice"], color=colores[banda],
                    label=f"{banda}: {d['registros_banda'].iat[0]:,} reg.")
        ax.set_title(esp, fontstyle="italic", fontsize=10.5)
        ax.legend(loc="upper left", fontsize=7.5, handlelength=1.2)
        ax.set_ylim(0, tope * 1.25)
        ax.set_xticks(range(1, 13), [m[0] for m in MESES])
    for ax in list(ejes.flat)[len(especies):]:
        ax.set_visible(False)
    fig.supylabel("Índice (1 = lo esperado por el esfuerzo del mes)",
                  fontsize=9.5, color=estilo.TINTA_2)
    fig.suptitle("Estacionalidad de murciélagos migratorios, corregida por esfuerzo de muestreo",
                 x=0.01, ha="left", fontsize=12, fontweight="semibold")
    fig.tight_layout()
    fig.savefig(destino)
    plt.close(fig)


# ─────────────────────────────────────────
# Ejecucion
# ─────────────────────────────────────────

def main(unidades, especies):
    SALIDA.mkdir(parents=True, exist_ok=True)
    estilo.aplicar()
    csv = {"encoding": "utf-8-sig"}
    df = preparar(unidades)
    print(f"{len(df):,} registros de especies nativas ({df['anio'].notna().mean():.0%} con año)")

    # D1
    dt = registros_decada_tipo(df)
    dt.to_csv(SALIDA / "registros_decada_tipo.csv", **csv)
    fig_decada_tipo(dt, SALIDA / "registros_decada_tipo.png")
    ez = esfuerzo_zona_decada(df, unidades)
    ez.to_csv(SALIDA / "esfuerzo_zona_decada.csv", **csv)
    fig_esfuerzo(ez, SALIDA / "esfuerzo_zona_decada.png")

    curvas, primeros = acumulacion_especies(df, unidades)
    curvas.to_csv(SALIDA / "acumulacion_especies.csv", index_label="anio", **csv)
    fig_acumulacion(curvas, SALIDA / "acumulacion_especies.png")
    sat = saturacion(curvas, primeros)
    sat.to_csv(SALIDA / "saturacion_zonas.csv", **csv)
    primeros.sort_values(["unidad", "primer_anio"], ascending=[True, False]).to_csv(
        SALIDA / "especies_nuevas_zona.csv", index=False, **csv)
    print("\n[D1] Registros por decada y tipo (miles):")
    print((dt.loc["1950s":] / 1000).round(1).to_string())
    print("\n[D1] Saturacion del inventario por zona:")
    print(sat.to_string())

    # D3
    est = estacionalidad(df, especies)
    est.to_csv(SALIDA / "estacionalidad.csv", index=False, **csv)
    fig_estacionalidad(est, especies, SALIDA / "estacionalidad.png")
    pico = est[est["registros_banda"] >= MIN_REGISTROS_BANDA].loc[
        lambda d: d.groupby(["especie", "banda"])["indice"].idxmax()]
    print("\n[D3] Mes de maximo indice por especie y banda:")
    print(pico.assign(mes=pico["mes"].map(lambda m: MESES[m - 1]))[
        ["especie", "banda", "mes", "indice", "registros_banda"]].to_string(index=False))
    print(f"\nSalidas en {SALIDA}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--unidades", nargs="+", default=list(ZONAS_UTM))
    parser.add_argument("--especies", nargs="+", default=MURCIELAGOS_MIGRATORIOS,
                        help="murcielagos para la estacionalidad (binomio)")
    args = parser.parse_args()
    main(args.unidades, args.especies)
