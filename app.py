import re
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

@app.route('/', methods=['GET','POST'])
def index():
    resumen_html  = None
    resumen_texto = None
    error_msg     = None
    total         = 0

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
        total=total
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
