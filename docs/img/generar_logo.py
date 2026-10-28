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
