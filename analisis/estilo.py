"""Estilo grafico comun a todos los analisis (matplotlib, PNG sobre fondo blanco).

Presentacion academica: fondo blanco, grises neutros, ejes oscuros y una paleta
de tonos profundos (no fluorescentes). Colores por unidad FIJOS: una zona
conserva su color en todas las figuras, aunque se grafique un subconjunto.

Paleta categorica validada sobre blanco con el validador de la guia dataviz
(OKLab): los pares adyacentes se separan con vision normal (dE >= 15) y con
daltonismo (dE >= 8.8); todos los tonos tienen contraste >= 3:1 con el fondo.
Entre pares no adyacentes el mas cercano es ocre/naranja (dE 12.5), por eso
las figuras con las siete zonas llevan leyenda y etiquetas directas.
"""
import matplotlib as mpl
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, to_rgb

from config import ZONAS_UTM

SUPERFICIE = "#ffffff"
TINTA = "#111111"
TINTA_2 = "#3d3d3d"
TINTA_TENUE = "#737373"
REJILLA = "#e5e5e5"
EJE = "#595959"
OTROS = "#a6a6a6"  # unidades sin slot propio

# azul, naranja quemado, verde, morado, ocre, carmin, azul petroleo, rojo
CATEGORICA = ["#1f5fa8", "#c85a19", "#1e8a5e", "#7b3fa8",
              "#8f7a00", "#c2306a", "#0e9fc0", "#b22b2b"]
AZUL = "#1f5fa8"

# Pasos discretos para mapas por clases
PASOS_SECUENCIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5",
                    "#256abf", "#184f95", "#0d366b"]
# rojo (menos) <- gris neutro -> azul (mas); mismo numero de pasos por brazo
PASOS_DIVERGENTE = ["#b3302f", "#e34948", "#f2a9a7", "#efefef",
                    "#9ec5f4", "#3987e5", "#1c5cab"]
NEUTRO = "#efefef"

# Rampa secuencial azul (claro -> oscuro) para heatmaps
SECUENCIAL = LinearSegmentedColormap.from_list(
    "azul", ["#f4f8fd", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5",
             "#256abf", "#184f95", "#0d366b"])


def colores_unidades(unidades):
    """Zonas UTM en orden oeste->este toman los slots 1-7; otras unidades
    (paises) toman los slots libres en el orden dado y despues gris."""
    colores = {z: CATEGORICA[i] for i, z in enumerate(ZONAS_UTM)}
    libres = iter(CATEGORICA[len(ZONAS_UTM):])
    for u in unidades:
        if u not in colores:
            colores[u] = next(libres, OTROS)
    return {u: colores[u] for u in unidades}


def cursiva(nombre):
    """Nombre cientifico en italica dentro de una etiqueta de matplotlib (mathtext),
    para mezclarlo con texto normal: f"{cursiva(e)} *  (EN)"."""
    return r"$\mathit{" + nombre.replace(" ", r"\ ") + "}$"


def tinta_sobre(color_fondo):
    """Blanco o tinta segun la luminancia del fondo (texto dentro de celdas)."""
    r, g, b = to_rgb(color_fondo)
    return "white" if 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.5 else TINTA


def aplicar():
    mpl.rcParams.update({
        "figure.facecolor": SUPERFICIE,
        "axes.facecolor": SUPERFICIE,
        "savefig.facecolor": SUPERFICIE,
        "savefig.dpi": 150,
        "savefig.bbox": "tight",
        "font.family": ["Segoe UI", "DejaVu Sans"],
        "font.size": 10,
        # mathtext (usado por cursiva()) con la misma fuente que el texto normal
        "mathtext.fontset": "custom",
        "mathtext.rm": "Segoe UI",
        "mathtext.it": "Segoe UI:italic",
        "mathtext.bf": "Segoe UI:bold",
        "text.color": TINTA,
        "axes.labelcolor": TINTA_2,
        "axes.titlesize": 12,
        "axes.titleweight": "semibold",
        "axes.titlelocation": "left",
        "axes.edgecolor": EJE,
        "axes.linewidth": 1,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": REJILLA,
        "grid.linewidth": 1,
        "grid.linestyle": "-",
        "axes.axisbelow": True,
        "xtick.color": TINTA_TENUE,
        "ytick.color": TINTA_TENUE,
        "xtick.labelcolor": TINTA_2,
        "ytick.labelcolor": TINTA_2,
        "lines.linewidth": 2,
        "lines.solid_capstyle": "round",
        "legend.frameon": False,
        "legend.labelcolor": TINTA_2,
    })


def heatmap(ax, matriz, fmt, vmax=None, mascara=None):
    """Heatmap anotado con la rampa secuencial; el texto cambia a blanco en celdas oscuras."""
    valores = matriz.to_numpy(dtype=float)
    if mascara is not None:
        valores = np.ma.masked_where(mascara, valores)
    im = ax.imshow(valores, cmap=SECUENCIAL, vmin=0,
                   vmax=vmax or np.nanmax(valores), aspect="auto")
    ax.set_xticks(range(matriz.shape[1]), matriz.columns)
    ax.set_yticks(range(matriz.shape[0]), matriz.index)
    ax.tick_params(length=0)
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    for i in range(matriz.shape[0]):
        for j in range(matriz.shape[1]):
            if mascara is not None and mascara[i, j]:
                continue
            v = matriz.iat[i, j]
            ax.text(j, i, format(v, fmt), ha="center", va="center", fontsize=8.5,
                    color=tinta_sobre(im.cmap(im.norm(v))))
    return im


MESES_ABREV = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
               "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def eje_meses(ax):
    """Eje x de enero (1) a diciembre (12) con los meses abreviados."""
    ax.set_xticks(range(1, 13), MESES_ABREV, fontsize=8)
    ax.set_xlim(0.5, 12.5)
