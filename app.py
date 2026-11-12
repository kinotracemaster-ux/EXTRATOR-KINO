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

# --- Unidad y precio de cada referencia ---------------------------------
# Encabezados de columna que se buscan en la página del PDF.
UNIT_HEADERS  = {'UNIDAD', 'UNIDADES', 'UND', 'UNID', 'U/M', 'UM', 'U.M.', 'MEDIDA'}
PRICE_HEADERS = {'PRECIO', 'P.UNIT', 'P.UNIT.', 'V.UNIT', 'V.UNIT.', 'VR.UNIT', 'VR.UNIT.'}
# Unidades reconocidas cuando la página no tiene encabezados.
UNIT_TOKENS   = {'UND', 'UNID', 'UNIDAD', 'UNIDADES', 'PAR', 'PARES', 'PZA', 'PZ', 'PIEZA',
                 'KG', 'CAJA', 'CJ', 'MT', 'MTS', 'LT', 'GL', 'ROLLO', 'PAQ', 'DOC',
                 'DOCENA', 'JGO', 'JUEGO', 'BOLSA', 'SET', 'KIT'}
PRICE_PAT     = re.compile(r'^\$?\s*\d[\d.,]*$')
QTY_PAT       = re.compile(r'^\d+[x×]')
LINE_TOL      = 3  # tolerancia vertical (pt) para considerar dos palabras en la misma fila


def _norm(txt):
    return txt.strip().upper().rstrip(':')


def find_columns(words):
    """Devuelve (anclas, x_unidad, x_precio) a partir de la fila de encabezados.

    Las anclas son todas las palabras de la fila de encabezados (x central),
    para poder asignar cada valor a su columna más cercana."""
    for w in words:
        t = _norm(w['text'])
        if t in UNIT_HEADERS or t in PRICE_HEADERS:
            fila = [h for h in words if abs(h['top'] - w['top']) <= LINE_TOL]
            # Una fila con cantidad (ej. 10x) es de datos, no de encabezados
            if any(QTY_PAT.match(h['text']) for h in fila):
                continue
            fila.sort(key=lambda h: h['x0'])
            anclas = [((h['x0'] + h['x1']) / 2, _norm(h['text'])) for h in fila]
            x_u = next((x for x, t in anclas if t in UNIT_HEADERS), None)
            x_p = next((x for x, t in anclas if t in PRICE_HEADERS), None)
            return anclas, x_u, x_p
    return None, None, None


def unidad_y_precio(words, code_word, columnas):
    """Busca unidad y precio en la misma fila del PDF, a la derecha del código.
    Si no se encuentran con certeza, devuelve cadena vacía (no se inventan datos)."""
    anclas, x_u, x_p = columnas
    fila = [w for w in words
            if abs(w['top'] - code_word['top']) <= LINE_TOL and w['x0'] > code_word['x1']]
    fila.sort(key=lambda w: w['x0'])
    unidad, precio = [], []
    if anclas and (x_u is not None or x_p is not None):
        for w in fila:
            xc = (w['x0'] + w['x1']) / 2
            cerca = min(anclas, key=lambda a: abs(a[0] - xc))[0]
            if x_u is not None and cerca == x_u:
                unidad.append(w['text'])
            elif x_p is not None and cerca == x_p:
                precio.append(w['text'])
    else:
        # Sin encabezados: precio = primer valor con '$'; unidad = palabra justo
        # antes del precio, solo si es una unidad conocida (ej. "UND $9.900").
        for i, w in enumerate(fila):
            if w['text'].startswith('$') and PRICE_PAT.match(w['text']):
                precio.append(w['text'])
                if i > 0 and _norm(fila[i-1]['text']) in UNIT_TOKENS:
                    unidad.append(fila[i-1]['text'])
                break
    return ' '.join(unidad), ' '.join(precio)

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
                                unidad, precio = unidad_y_precio(words, w, columnas)
                                datos.append({'codigo': codigo, 'cantidad': cantidad,
                                              'unidad': unidad, 'precio': precio})
                                continue
                            # 2) ¿Solo cantidad? entonces tomo la siguiente palabra como código
                            m2 = qty_only_pat.match(txt)
                            if m2 and idx + 1 < len(words):
                                cantidad = int(m2.group(1))
                                codigo   = words[idx+1]['text']
                                # validamos que el token “parezca” código
                                if re.match(r'^[A-Za-z0-9][A-Za-z0-9:.\-]*$', codigo):
                                    unidad, precio = unidad_y_precio(words, words[idx+1], columnas)
                                    datos.append({'codigo': codigo, 'cantidad': cantidad,
                                                  'unidad': unidad, 'precio': precio})

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
