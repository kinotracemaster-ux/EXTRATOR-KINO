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

@app.route('/', methods=['GET','POST'])
def index():
    resumen_html = None
    error_msg    = None
    total        = 0

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
                        for idx, w in enumerate(words):
                            txt = w['text']
                            # 1) ¿Cantidad+Código en la misma palabra?
                            m1 = combined_pat.match(txt)
                            if m1:
                                cantidad = int(m1.group(1))
                                codigo   = m1.group(2)
                                datos.append({'codigo': codigo, 'cantidad': cantidad})
                                continue
                            # 2) ¿Solo cantidad? entonces tomo la siguiente palabra como código
                            m2 = qty_only_pat.match(txt)
                            if m2 and idx + 1 < len(words):
                                cantidad = int(m2.group(1))
                                codigo   = words[idx+1]['text']
                                # validamos que el token “parezca” código
                                if re.match(r'^[A-Za-z0-9][A-Za-z0-9:.\-]*$', codigo):
                                    datos.append({'codigo': codigo, 'cantidad': cantidad})

                total = len(datos)
                if total == 0:
                    error_msg = "No se hallaron códigos/cantidades en el PDF."
                else:
                    df = pd.DataFrame(datos, columns=['codigo','cantidad'])
                    # Agregar columna vacía en el medio para estética
                    df.insert(1, '', '')
                    resumen_html = df.to_html(index=False)

            except Exception as e:
                error_msg = f"Error al procesar el PDF: {e}"

    return render_template(
        'index.html',
        resumen_html=resumen_html,
        error=error_msg,
        total=total
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
