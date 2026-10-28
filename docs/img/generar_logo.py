"""Genera el logo de poblar (SVG, texto convertido a curvas con Inter Display, licencia OFL).

Uso: python generar_logo.py  (escribe los SVG en la carpeta actual).
"""
import sys
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

def palabra(texto, fuente, alto_px, x0, base_y, tracking=0):
    f = TTFont(fuente); gs = f.getGlyphSet(); cmap = f.getBestCmap()
    upm = f['head'].unitsPerEm; esc = alto_px / upm
    d = []; x = x0
    for ch in texto:
        g = cmap[ord(ch)]; pen = SVGPathPen(gs)
        tp = TransformPen(pen, (esc, 0, 0, -esc, x, base_y))
        gs[g].draw(tp); d.append(pen.getCommands())
        x += gs[g].width * esc + tracking
    return " ".join(d), x

# Isotipo: grilla 4x4; cada celda tiene un cuadrado de tamaño proporcional a la densidad
# (reparto dasimétrico): denso arriba a la derecha, disperso abajo a la izquierda.
DENS = [[.30,.55,.85,1.0],
        [.20,.40,.75,.90],
        [.12,.25,.45,.60],
        [.0,.12,.20,.32]]
def isotipo(x0, y0, celda, colores):
    r = []
    for i, fila in enumerate(DENS):
        for j, v in enumerate(fila):
            cx, cy = x0 + j*celda + celda/2, y0 + i*celda + celda/2
            if v == 0:
                lado = celda*0.22; color = colores['vacio']
            else:
                lado = celda*(0.28 + 0.64*v); color = colores['alto'] if v >= .7 else colores['medio'] if v >= .35 else colores['bajo']
            rr = lado*0.18
            r.append(f'<rect x="{cx-lado/2:.2f}" y="{cy-lado/2:.2f}" width="{lado:.2f}" height="{lado:.2f}" rx="{rr:.2f}" fill="{color}"/>')
    return "\n  ".join(r)

FUENTE = "/usr/share/fonts/opentype/inter/InterDisplay-SemiBold.otf"
def logo(tema, salida, con_texto=True, lema=False):
    c = {"claro": dict(alto="#4a2f7a", medio="#8a5cd6", bajo="#c49a5a", vacio="#ddd3c0", texto="#1d1b18", suave="#6b665e"),
         "oscuro": dict(alto="#c4adf0", medio="#9b6be6", bajo="#b88c4f", vacio="#4a443a", texto="#ecebe7", suave="#a59f97")}[tema]
    celda = 15; iso = isotipo(0, 0, celda, c)
    if not con_texto:
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 60" width="60" height="60" role="img" aria-label="poblar">\n  {iso}\n</svg>\n'
    else:
        d, xfin = palabra("poblar", FUENTE, 62, 76, 44, tracking=-0.6)
        ancho = xfin + 4; alto = 60
        extra = ""
        if lema:
            d2, x2 = palabra("población expuesta a la degradación de tierras", "/usr/share/fonts/opentype/inter/InterDisplay-Medium.otf", 13.5, 77, 76, tracking=0.1)
            extra = f'\n  <path d="{d2}" fill="{c["suave"]}"/>'; ancho = max(ancho, x2 + 4); alto = 84
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho:.0f} {alto}" width="{ancho:.0f}" height="{alto}" role="img" aria-label="poblar">\n'
               f'  {iso}\n  <path d="{d}" fill="{c["texto"]}"/>{extra}\n</svg>\n')
    open(salida, "w").write(svg)

logo("claro", "poblar.svg", lema=True)
logo("oscuro", "poblar_oscuro.svg", lema=True)
logo("claro", "isotipo.svg", con_texto=False)
logo("oscuro", "isotipo_oscuro.svg", con_texto=False)


def banner(salida, ancho=1200, alto=240):
    """Banner horizontal (cuaderno de Colab, presentaciones): isologotipo a la izquierda y campo de píxeles a la derecha."""
    import math
    import random
    c = dict(fondo="#f7f5f0", linea="#e6e0d4", alto="#4a2f7a", medio="#8a5cd6", bajo="#c49a5a", vacio="#ddd3c0",
             texto="#1d1b18", suave="#6b665e")
    celda = 26
    iso = isotipo(64, (alto - 4 * celda) / 2, celda, c)
    d, xfin = palabra("poblar", FUENTE, 104, 196, 136, tracking=-1.0)
    d2, _ = palabra("población expuesta a la degradación de tierras", FUENTE.replace("SemiBold", "Medium"), 22, 199, 176, tracking=0.1)
    d3, _ = palabra("censo por radio · cobertura del suelo · degradación → indicadores SO2 de la CNULD",
                    FUENTE.replace("SemiBold", "Regular"), 14.5, 199, 204, tracking=0.2)
    # Campo de píxeles: densidad alrededor de dos núcleos, se desvanece hacia la izquierda
    random.seed(7)
    paso, cuadros = 22, []
    x_ini = 760
    for x in range(x_ini, ancho + paso, paso):
        for y in range(-paso, alto + paso, paso):
            dist = min(math.hypot(x - 1000, y - 80), math.hypot(x - 1135, y - 185) * 1.25, math.hypot(x - 880, y - 175) * 1.8)
            dens = max(0.0, 1 - dist / 170) + random.uniform(-0.1, 0.1)
            if dens <= 0.05 and random.random() < 0.55:
                dens = random.uniform(0.15, 0.4)   # tierra con poca gente
            desv = min(1.0, (x - x_ini) / 220)
            if dens <= 0.05:
                lado, color = 3.0, c["vacio"]
            else:
                lado = 4 + 13 * min(dens, 1)
                color = c["alto"] if dens > 0.72 else c["medio"] if dens > 0.42 else c["bajo"]
            op = 0.9 * desv
            cuadros.append(f'<rect x="{x - lado / 2:.1f}" y="{y - lado / 2:.1f}" width="{lado:.1f}" height="{lado:.1f}" '
                           f'rx="{lado * 0.18:.1f}" fill="{color}" opacity="{op:.2f}"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho} {alto}" width="{ancho}" height="{alto}" '
           f'role="img" aria-label="poblar · población expuesta a la degradación de tierras">\n'
           f'  <defs><clipPath id="m"><rect width="{ancho}" height="{alto}" rx="18"/></clipPath></defs>\n'
           f'  <g clip-path="url(#m)">\n  <rect width="{ancho}" height="{alto}" fill="{c["fondo"]}"/>\n  '
           + "\n  ".join(cuadros) + "\n  </g>\n"
           f'  <rect x="0.5" y="0.5" width="{ancho - 1}" height="{alto - 1}" rx="18" fill="none" stroke="{c["linea"]}"/>\n'
           f'  {iso}\n  <path d="{d}" fill="{c["texto"]}"/>\n  <path d="{d2}" fill="{c["suave"]}"/>\n'
           f'  <path d="{d3}" fill="{c["suave"]}" opacity="0.85"/>\n</svg>\n')
    open(salida, "w").write(svg)


banner("banner.svg")
