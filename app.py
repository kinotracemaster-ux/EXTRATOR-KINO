import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import os
import pandas as pd
import pdfplumber
from flask import Flask, request, render_template
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(fn):
    return '.' in fn and fn.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Precio de cada referencia --------------------------------------------
# La columna UNIDAD siempre muestra este texto en todas las filas.
UNIDAD_FIJA   = 'UNIDAD'
# Encabezados de la columna de precio que se buscan en la página del PDF.
PRICE_HEADERS = {'PRECIO', 'P.UNIT', 'P.UNIT.', 'V.UNIT', 'V.UNIT.', 'VR.UNIT', 'VR.UNIT.'}
PRICE_PAT     = re.compile(r'^\$?\s*\d[\d.,]*$')
QTY_PAT       = re.compile(r'^\d+[x×]')
CODE_PAT      = re.compile(r'^[A-Za-z0-9][A-Za-z0-9:.\-]*$')
LINE_TOL      = 3  # tolerancia vertical (pt) para considerar dos palabras en la misma fila


def _norm(txt):
    return txt.strip().upper().rstrip(':')


def find_columns(words):
    """Devuelve (anclas, x_precio) a partir de la fila de encabezados.

    Las anclas son todas las palabras de la fila de encabezados (x central),
    para poder asignar cada valor a su columna más cercana."""
    for w in words:
        if _norm(w['text']) in PRICE_HEADERS:
            fila = [h for h in words if abs(h['top'] - w['top']) <= LINE_TOL]
            # Una fila con cantidad (ej. 10x) es de datos, no de encabezados
            if any(QTY_PAT.match(h['text']) for h in fila):
                continue
            fila.sort(key=lambda h: h['x0'])
            anclas = [((h['x0'] + h['x1']) / 2, _norm(h['text'])) for h in fila]
            x_p = next((x for x, t in anclas if t in PRICE_HEADERS), None)
            return anclas, x_p
    return None, None


def leer_precio(precio):
    """Interpreta un precio del PDF ('$72,000.00', '$1.000,50', '3.200').
    Devuelve (valor, formato) o None si no se puede leer."""
    m = re.match(r'^(\$?\s*)(\d[\d.,]*)$', (precio or '').strip())
    if not m:
        return None
    pref, num = m.groups()
    # Separador decimal: el último '.' o ',' seguido de 1-2 dígitos al final
    dm = re.search(r'([.,])(\d{1,2})$', num)
    dec_sep = dm.group(1) if dm else None
    decs = len(dm.group(2)) if dm else 0
    miles_sep = ',' if dec_sep == '.' else '.' if dec_sep == ',' else (
        ',' if ',' in num else '.' if '.' in num else '')
    entero = num[:dm.start()] if dm else num
    try:
        valor = Decimal(entero.replace(miles_sep, '') if miles_sep else entero)
        if dm:
            valor += Decimal('0.' + dm.group(2))
    except InvalidOperation:
        return None
    return valor, (pref, dec_sep, miles_sep, decs)


def formatear_precio(valor, formato):
    """Escribe un valor con el mismo formato (símbolo, miles, decimales) del PDF."""
    pref, dec_sep, miles_sep, decs = formato
    valor = valor.quantize(Decimal(1).scaleb(-decs), rounding=ROUND_HALF_UP)
    txt = f'{valor:,.{decs}f}'  # formato 1,234.56
    if miles_sep != ',':
        txt = txt.replace(',', '\0').replace('.', ',' if dec_sep == ',' else '.').replace('\0', miles_sep)
    return pref + txt


# --- Datos del pedido para verificación (fuera de la tabla, no se copian) ---
PEDIDO_PAT = re.compile(r'\b(?:RECIBO|PEDIDO|ORDEN|FACTURA|COTIZACI[OÓ]N)\b\s*(?:N[°ºo.]*\s*)?#?\s*:?\s*([A-Za-z0-9][A-Za-z0-9-]*)', re.I)
TOTAL_PAT  = re.compile(r'^\s*TOTAL\s*:?\s*(\$?\s*\d[\d.,]*)\s*$', re.I)
CANT_PAT   = re.compile(r'Cant\.?\s*:\s*(\d+)', re.I)          # unidades (suma de cantidades)
ART_PAT    = re.compile(r'\b(\d+)\s+art[ií]culos?\b', re.I)     # líneas / referencias
CLIENTE_PAT = re.compile(r'^\s*CLIENTE\s*:\s*(.+)$', re.I)
FECHA_PAT  = re.compile(r'\b(\d{1,2} de [A-Za-záéíóúñ]+ de \d{4}(?:,?\s+\d{1,2}:\d{2})?'
                        r'|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}(?:\s+\d{1,2}:\d{2})?)', re.I)


def _negrita(linea):
    return any(k in linea['chars'][0]['fontname'].lower() for k in ('bold', 'semibold', 'black'))


def datos_pedido(pdf):
    """Busca en el PDF número de pedido, cliente, fecha, total y cantidad de
    artículos. Lo que no aparezca queda como ''."""
    datos = {'pedido': '', 'cliente': '', 'fecha': '', 'total': '', 'articulos': '', 'unidades': ''}
    lineas = []
    for page in pdf.pages:
        lineas.extend(page.extract_text_lines())
    textos = [l['text'] for l in lineas]

    for t in textos:
        if not datos['pedido']:
            m = PEDIDO_PAT.search(t)
            if m and any(ch.isdigit() for ch in m.group(1)):
                datos['pedido'] = m.group(1)
        if not datos['unidades']:
            m = CANT_PAT.search(t)
            if m:
                datos['unidades'] = m.group(1)
        if not datos['articulos']:
            m = ART_PAT.search(t)
            if m:
                datos['articulos'] = m.group(1)
        if not datos['cliente']:
            m = CLIENTE_PAT.match(t)
            if m:
                datos['cliente'] = m.group(1).strip()
        m = TOTAL_PAT.match(t)
        if m:
            datos['total'] = m.group(1).strip()   # el último "Total" del PDF
        m = FECHA_PAT.search(t)
        if m:
            datos['fecha'] = m.group(1)           # la última fecha del PDF

    # Sin etiqueta "Cliente:": en el encabezado (antes del primer artículo) el
    # primer nombre en negrita es el vendedor y el segundo, del mismo tamaño, el cliente.
    if not datos['cliente'] and lineas:
        encabezado = []
        for l in lineas:
            if QTY_PAT.match(l['text']) or CANT_PAT.search(l['text']):
                break
            if PEDIDO_PAT.search(l['text']) or not l['chars']:
                continue
            if _negrita(l):
                encabezado.append(l)
        if len(encabezado) >= 2:
            vendedor, cliente = encabezado[0], encabezado[1]
            if round(vendedor['chars'][0]['size']) == round(cliente['chars'][0]['size']):
                datos['cliente'] = cliente['text'].strip()
    return datos



# --- Lectura de artículos como una lista continua --------------------------
# Todas las páginas se leen como una sola secuencia de líneas, así un artículo
# partido por un salto de página (cantidad abajo, código en la página siguiente)
# o con la descripción en varias líneas se arma igual.
QTY_WORD   = re.compile(r'^(\d+)[x×]$')
QTY_CODE   = re.compile(r'^(\d+)[x×]([A-Za-z0-9][A-Za-z0-9:.\-]*)$')
FIN_PAT    = re.compile(r'^\s*(TOTAL|SUBTOTAL|OTROS)\b', re.I)


def _codigo_suelto(t):
    """Código al inicio de una línea sin cantidad delante: debe tener un dígito y
    una letra o guion (810-C1, 312-1, A10), para no confundirlo con números sueltos."""
    return bool(CODE_PAT.match(t)) and any(c.isdigit() for c in t) and \
        any(c.isalpha() or c == '-' for c in t)


def lineas_continuas(pdf):
    lineas = []
    for n, page in enumerate(pdf.pages, 1):
        words = page.extract_words(use_text_flow=True)
        cols = find_columns(words)
        grupos = []
        for w in sorted(words, key=lambda w: w['top']):
            if grupos and abs(w['top'] - grupos[-1]['top']) <= LINE_TOL:
                grupos[-1]['words'].append(w)
            else:
                grupos.append({'top': w['top'], 'words': [w]})
        for g in grupos:
            g['words'].sort(key=lambda w: w['x0'])
            g.update(pagina=n, cols=cols, texto=' '.join(w['text'] for w in g['words']))
            lineas.append(g)
    return lineas


def _es_precio(w, cols):
    anclas, x_p = cols
    if anclas and x_p is not None:
        cerca = min(anclas, key=lambda a: abs(a[0] - (w['x0'] + w['x1']) / 2))[0]
        return cerca == x_p and bool(PRICE_PAT.match(w['text']))
    return w['text'].startswith('$') and bool(PRICE_PAT.match(w['text']))


def leer_articulos(pdf):
    """Devuelve (datos, mapa, avisos).
    datos: artículos {codigo, cantidad, unidad, precio} en el orden del PDF.
    mapa:  cada línea del PDF con su página y lo que se entendió de ella.
    avisos: posibles problemas (cantidad sin código, código sin cantidad, ...)."""
    lineas = lineas_continuas(pdf)
    inicio = next((i + 1 for i, l in enumerate(lineas) if ART_PAT.search(l['texto'])), 0)
    datos, avisos = [], []
    mapa = [{'pagina': l['pagina'], 'texto': l['texto'], 'tipo': ''} for l in lineas]
    actual = None
    fin = False

    def cerrar():
        if not actual:
            return
        if actual['cantidad'] is not None and actual['codigo']:
            datos.append({'codigo': actual['codigo'], 'cantidad': actual['cantidad'],
                          'unidad': UNIDAD_FIJA, 'precio': actual['precio']})
            paginas = sorted({lineas[i]['pagina'] for i in actual['lineas']})
            for i in actual['lineas']:
                mapa[i]['tipo'] = f"Artículo {actual['codigo']}"
                if len(paginas) > 1:
                    mapa[i]['tipo'] += ' (partido entre páginas)'
            if not actual['precio']:
                avisos.append(f"{actual['codigo']}: no se encontró su precio.")
        elif actual['cantidad'] is not None:
            pag = lineas[min(actual['lineas'])]['pagina']
            texto = lineas[min(actual['lineas'])]['texto']
            avisos.append(f"Página {pag}: «{texto}» tiene cantidad {actual['cantidad']}x pero no se encontró "
                          f"su código; no se incluyó.")
            for i in actual['lineas']:
                mapa[i]['tipo'] = '⚠ Cantidad sin código'
        elif actual['codigo']:
            pag = lineas[min(actual['lineas'])]['pagina']
            texto = lineas[min(actual['lineas'])]['texto']
            avisos.append(f"Página {pag}: «{texto}» empieza como un código ({actual['codigo']}) pero no tiene "
                          f"cantidad; no se incluyó. Revisar si es una referencia o parte de una descripción.")
            for i in actual['lineas']:
                mapa[i]['tipo'] = '⚠ Código sin cantidad'

    def nuevo():
        return {'cantidad': None, 'codigo': '', 'precio': '', 'lineas': set()}

    for i, l in enumerate(lineas):
        if i < inicio:
            mapa[i]['tipo'] = 'Encabezado'
            continue
        if fin:
            mapa[i]['tipo'] = 'Pie'
            continue
        if FIN_PAT.match(l['texto']):
            cerrar()
            actual = None
            fin = True
            mapa[i]['tipo'] = 'Total'
            continue
        prev_qty = False
        for k, w in enumerate(l['words']):
            t = w['text']
            m = QTY_CODE.match(t)
            mq = QTY_WORD.match(t)
            if m or mq:
                ws = l['words']
                con_codigo = bool(m) or (k + 1 < len(ws) and CODE_PAT.match(ws[k + 1]['text']))
                # "5x CODIGO" en la misma línea siempre abre un artículo nuevo; una
                # cantidad sola completa el código pendiente (descripción en varias
                # líneas o código en la página anterior).
                if actual is None or actual['cantidad'] is not None or con_codigo:
                    cerrar()
                    actual = nuevo()
                actual['cantidad'] = int((m or mq).group(1))
                actual['lineas'].add(i)
                if m:
                    actual['codigo'] = m.group(2)
                prev_qty = bool(mq)
                continue
            if (prev_qty and CODE_PAT.match(t)) or (k == 0 and _codigo_suelto(t)):
                if actual is None or (actual['codigo'] and not prev_qty):
                    cerrar()
                    actual = nuevo()
                actual['codigo'] = t
                actual['lineas'].add(i)
            elif actual and not actual['precio'] and i in actual['lineas'] and _es_precio(w, l['cols']):
                actual['precio'] = t
            prev_qty = False
        if not mapa[i]['tipo'] and (actual is None or i not in actual['lineas']):
            mapa[i]['tipo'] = 'Descripción'
    cerrar()
    return datos, mapa, avisos


@app.route('/', methods=['GET','POST'])
def index():
    resumen_html  = None
    resumen_texto = None
    error_msg     = None
    total         = 0
    pedido        = None
    mapa          = None

    if request.method == 'POST':
        f = request.files.get('pdf')
        if not f or not allowed_file(f.filename):
            error_msg = "Sube un PDF válido."
        else:
            fn   = secure_filename(f.filename)
            path = os.path.join(app.config['UPLOAD_FOLDER'], fn)
            f.save(path)

            try:
                mapa, avisos = [], []
                with pdfplumber.open(path) as pdf:
                    pedido = datos_pedido(pdf)
                    datos, mapa, avisos = leer_articulos(pdf)
                pedido['avisos'] = avisos

                total = len(datos)
                if total == 0:
                    error_msg = "No se hallaron códigos/cantidades en el PDF."
                else:
                    df = pd.DataFrame(datos, columns=['codigo','cantidad','unidad','precio'])
                    pedido['unidades_ext'] = int(df['cantidad'].sum())
                    # Verificación: suma de los precios extraídos frente al Total del PDF
                    leidos = [leer_precio(p) for p in df['precio']]
                    validos = [x for x in leidos if x]
                    if validos:
                        ref = leer_precio(pedido['total']) or validos[0]
                        suma = sum(x[0] for x in validos)
                        # Si PRECIO es unitario, el total del PDF es la suma de cantidad x precio
                        suma_cant = sum(x[0] * q for x, q in zip(leidos, df['cantidad']) if x)
                        total_pdf = leer_precio(pedido['total'])
                        if total_pdf and suma != total_pdf[0] and suma_cant == total_pdf[0]:
                            suma = suma_cant
                            pedido['suma_x_cant'] = True
                        pedido['suma'] = formatear_precio(suma, ref[1])
                        pedido['sin_precio'] = len(leidos) - len(validos)
                        if total_pdf:
                            pedido['cuadra'] = suma == total_pdf[0]
                    # Revisión: descuadres y avisos, para mostrarlos arriba
                    revision = []
                    if pedido.get('cuadra') is False:
                        dif = leer_precio(pedido['total'])[0] - leer_precio(pedido['suma'])[0]
                        fmt = leer_precio(pedido['total'])[1]
                        revision.append(f"La suma de precios ({pedido['suma']}) no coincide con el Total del PDF "
                                        f"({pedido['total']}): {'faltan' if dif > 0 else 'sobran'} "
                                        f"{formatear_precio(abs(dif), fmt)}.")
                    if pedido['articulos'] and int(pedido['articulos']) != total:
                        n = int(pedido['articulos']) - total
                        revision.append(f"El PDF indica {pedido['articulos']} artículos y se extrajeron {total}: "
                                        f"{'faltan' if n > 0 else 'sobran'} {abs(n)}.")
                    if pedido['unidades'] and int(pedido['unidades']) != pedido['unidades_ext']:
                        n = int(pedido['unidades']) - pedido['unidades_ext']
                        revision.append(f"El PDF indica {pedido['unidades']} unidades y se extrajeron "
                                        f"{pedido['unidades_ext']}: {'faltan' if n > 0 else 'sobran'} {abs(n)}.")
                    pedido['revision'] = revision + avisos
                    # Texto plano para copiar (codigo \t vacío \t cantidad \t unidad \t vacío \t precio),
                    # sin titulos. En pantalla, el botón Copiar lo regenera desde la tabla (orden actual).
                    lines = []
                    for _, row in df.iterrows():
                        lines.append(f"{row['codigo']}\t\t{row['cantidad']}\t{row['unidad']}\t\t{row['precio']}")
                    resumen_texto = '\n'.join(lines)
                    # Columnas vacías de separación: tras el código y entre UNIDAD y PRECIO
                    df.insert(1, '', '')
                    df.insert(4, ' ', '')
                    df.columns = ['codigo', '', 'cantidad', 'UNIDAD', '', 'PRECIO']
                    resumen_html = df.to_html(index=False, table_id='results-table')

            except Exception as e:
                error_msg = f"Error al procesar el PDF: {e}"

    return render_template(
        'index.html',
        resumen_html=resumen_html,
        resumen_texto=resumen_texto,
        error=error_msg,
        total=total,
        pedido=pedido,
        mapa=mapa
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
