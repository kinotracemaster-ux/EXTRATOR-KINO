# PDF Table Extractor

Una app Flask que recibe un PDF con tablas, extrae de la columna 0 las cantidades (ej. `10x`) y de la columna 1 los códigos (todo hasta el primer espacio), agrupa y suma por código, y muestra los totales.

## Cómo usar localmente

```bash
git clone https://github.com/tu-usuario/pdf-extractor.git
cd pdf-extractor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export FLASK_APP=app.py
flask run
```

Luego abre <http://localhost:5000>.

## Deploy en Render.com

1. Crea cuenta en [Render.com](https://render.com) y conecta tu GitHub.
2. Nuevo **Web Service** → selecciona este repo.
3. Build Command:
   ```
   pip install -r requirements.txt
   ```
4. Start Command:
   ```
   gunicorn app:app
   ```
5. Despliega y visita la URL asignada.

¡Y voilà! Tu extractor de tablas PDF ya vuela en la nube. 🚀
