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


def precio_de_fila(words, qty_word, code_word, columnas):
    """Busca el precio a la derecha del código, en la misma fila que la cantidad
    o que el código (en algunos PDF el precio va alineado con la cantidad y el
    código queda un poco más arriba). Si no se encuentra, devuelve ''."""
    anclas, x_p = columnas
    tops = {qty_word['top'], code_word['top']}
    fila = [w for w in words
            if w['x0'] > code_word['x1']
            and any(abs(w['top'] - t) <= LINE_TOL for t in tops)]
    fila.sort(key=lambda w: w['x0'])
    if anclas and x_p is not None:
        precio = [w['text'] for w in fila
                  if min(anclas, key=lambda a: abs(a[0] - (w['x0'] + w['x1']) / 2))[0] == x_p]
        return ' '.join(precio)
    # Sin encabezados: precio = primer valor con '$'
    for w in fila:
        if w['text'].startswith('$') and PRICE_PAT.match(w['text']):
            return w['text']
    return ''

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
CANT_PAT   = re.compile(r'Cant\.?\s*:\s*(\d+)', re.I)
CLIENTE_PAT = re.compile(r'^\s*CLIENTE\s*:\s*(.+)$', re.I)
FECHA_PAT  = re.compile(r'\b(\d{1,2} de [A-Za-záéíóúñ]+ de \d{4}(?:,?\s+\d{1,2}:\d{2})?'
                        r'|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}(?:\s+\d{1,2}:\d{2})?)', re.I)


def _negrita(linea):
    return any(k in linea['chars'][0]['fontname'].lower() for k in ('bold', 'semibold', 'black'))


def datos_pedido(pdf):
    """Busca en el PDF número de pedido, cliente, fecha, total y cantidad de
    artículos. Lo que no aparezca queda como ''."""
    datos = {'pedido': '', 'cliente': '', 'fecha': '', 'total': '', 'articulos': ''}
    lineas = []
    for page in pdf.pages:
        lineas.extend(page.extract_text_lines())
    textos = [l['text'] for l in lineas]

    for t in textos:
        if not datos['pedido']:
            m = PEDIDO_PAT.search(t)
            if m and any(ch.isdigit() for ch in m.group(1)):
                datos['pedido'] = m.group(1)
        if not datos['articulos']:
            m = CANT_PAT.search(t)
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


@app.route('/', methods=['GET','POST'])
def index():
    resumen_html  = None
    resumen_texto = None
    error_msg     = None
    total         = 0
    pedido        = None

    if request.method == 'POST':
        f = request.files.get('pdf')
        if not f or not allowed_file(f.filename):
            error_msg = "Sube un PDF válido."
        else:
            fn   = secure_filename(f.filename)
            path = os.path.join(app.config['UPLOAD_FOLDER'], fn)
            f.save(path)

            try:
                datos = []
                # Patrón unificado: captura cantidad y código pegados o separados
                combined_pat = re.compile(r'^(\d+)[x×]\s*([A-Za-z0-9][A-Za-z0-9:.\-]*)$')
                # Patrón solo cantidad (para fallback)
                qty_only_pat = re.compile(r'^(\d+)[x×]\s*$')

                with pdfplumber.open(path) as pdf:
                    pedido = datos_pedido(pdf)
                    for page in pdf.pages:
                        words = page.extract_words(use_text_flow=True)
                        columnas = find_columns(words)
                        for idx, w in enumerate(words):
                            txt = w['text']
                            # 1) ¿Cantidad+Código en la misma palabra?
                            m1 = combined_pat.match(txt)
                            if m1:
                                cantidad = int(m1.group(1))
                                codigo   = m1.group(2)
                                precio = precio_de_fila(words, w, w, columnas)
                                datos.append({'codigo': codigo, 'cantidad': cantidad,
                                              'unidad': UNIDAD_FIJA, 'precio': precio})
                                continue
                            # 2) ¿Solo cantidad? entonces tomo la siguiente palabra como código
                            m2 = qty_only_pat.match(txt)
                            if m2 and idx + 1 < len(words):
                                cantidad = int(m2.group(1))
                                codigo   = words[idx+1]['text']
                                # validamos que el token “parezca” código
                                if re.match(r'^[A-Za-z0-9][A-Za-z0-9:.\-]*$', codigo):
                                    precio = precio_de_fila(words, w, words[idx+1], columnas)
                                    datos.append({'codigo': codigo, 'cantidad': cantidad,
                                                  'unidad': UNIDAD_FIJA, 'precio': precio})

                total = len(datos)
                if total == 0:
                    error_msg = "No se hallaron códigos/cantidades en el PDF."
                else:
                    df = pd.DataFrame(datos, columns=['codigo','cantidad','unidad','precio'])
                    # Verificación: suma de los precios extraídos frente al Total del PDF
                    leidos = [leer_precio(p) for p in df['precio']]
                    validos = [x for x in leidos if x]
                    if validos:
                        ref = leer_precio(pedido['total']) or validos[0]
                        suma = sum(v for v, _ in validos)
                        pedido['suma'] = formatear_precio(suma, ref[1])
                        pedido['sin_precio'] = len(leidos) - len(validos)
                        if pedido['total'] and leer_precio(pedido['total']):
                            pedido['cuadra'] = suma == leer_precio(pedido['total'])[0]
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
        pedido=pedido
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
