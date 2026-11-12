# Extractor de Códigos PDF: funcionamiento

Aplicación web (Flask) que lee un recibo o pedido en PDF y devuelve el listado de referencias con su cantidad y precio, listo para pegar en una hoja de cálculo. También revisa que lo extraído cuadre con lo que dice el PDF y avisa de cualquier problema.

---

## 1. Qué logra

- Convierte un recibo PDF de varias páginas en un listado limpio: **código, cantidad, unidad y precio**.
- Copia el listado al portapapeles, con tabulaciones, para pegarlo en Excel o Google Sheets sin que se descuadren las columnas.
- Ordena las referencias de forma natural (A2 antes de A10) cuando se le pide.
- Calcula un precio con descuento (por defecto 40 %) y deja elegir el porcentaje.
- Muestra los datos del pedido (número, cliente, fecha y total) para identificarlo.
- **Verifica** el resultado contra el propio PDF (total en dinero, número de artículos y unidades) e indica arriba, en «Revisión», cualquier error o descuadre.
- Enseña un **Mapa del PDF**: qué se entendió de cada línea, para encontrar rápido dónde está un problema.

---

## 2. Cómo se usa

1. Abre la app y arrastra el PDF (o haz clic para elegirlo).
2. Pulsa **Procesar PDF**.
3. Revisa el recuadro **Revisión**:
   - verde: todo cuadra;
   - rojo: lista los puntos a revisar.
4. (Opcional) Marca **Mostrar precio** y/o **Mostrar precio con descuento** y elige el porcentaje.
5. (Opcional) Pulsa **Organizar listado** para ordenar las referencias.
6. Pulsa **Copiar Resultado** y pega en la hoja de cálculo.
7. **Limpiar** vuelve al inicio.

---

## 3. Qué muestra la pantalla

### 3.1 Revisión (arriba)
Lista, uno por línea, los problemas detectados:

| Aviso | Qué significa |
|---|---|
| La suma de precios no coincide con el Total: faltan/sobran $X | La suma de PRECIO extraído no da el «Total» del PDF. Falta o sobra algún artículo o precio. |
| El PDF indica N artículos y se extrajeron M | No coincide el número de líneas del recibo («N artículos»). |
| El PDF indica U unidades y se extrajeron V | No coincide la suma de cantidades («Cant.: U»). |
| «…» empieza como un código pero no tiene cantidad | Una línea parece una referencia sin cantidad. Puede ser parte de una descripción (ej. «18K-GOLD»). No se incluyó. |
| «…» tiene cantidad Nx pero no se encontró su código | Hay una cantidad suelta. No se incluyó. |
| CÓDIGO: no se encontró su precio | El artículo se incluyó con la celda de precio vacía. |

Si el PDF no trae Total, número de artículos ni unidades, no hay nada contra qué comparar y el recuadro no aparece.

### 3.2 Códigos encontrados
Número de filas extraídas.

### 3.3 Datos del pedido (verificación)
No se copian; son solo para identificar y comprobar.

- **N.º de pedido**: lo que sigue a RECIBO / PEDIDO / ORDEN / FACTURA / COTIZACIÓN `#`.
- **Cliente**: lo que sigue a «Cliente:»; si no hay etiqueta, el segundo nombre en negrita del encabezado (el primero es el vendedor).
- **Fecha**: la última fecha del PDF (ej. «11 de noviembre de 2026 11:59» o dd/mm/aaaa).
- **Total del PDF**: el último «Total:».
- **Suma de PRECIO**: suma de los precios extraídos, con ✓/✗ frente al Total. Si el PDF usa precio unitario, compara con CANTIDAD × PRECIO.
- **Referencias (PDF / extraídas)**: «N artículos» frente a las filas extraídas.
- **Unidades (PDF / extraídas)**: «Cant.: U» frente a la suma de CANTIDAD.
- **Mapa del PDF** (plegable): cada línea con su página y cómo se interpretó: Encabezado, Artículo X, Artículo X (partido entre páginas), Descripción, ⚠ aviso, Total, Pie. Los saltos de página se marcan con una línea punteada.

Lo que no aparece en el PDF queda vacío; nunca se inventa.

### 3.4 Tabla de resultados

| Columna | Contenido | ¿Visible por defecto? |
|---|---|---|
| codigo | Referencia tal como está en el PDF | Sí |
| (vacía) | Separador | Sí |
| cantidad | Número antes de la «x» (ej. `5x` → 5) | Sí |
| UNIDAD | Siempre el texto «UNIDAD» | Sí |
| (vacía) | Separador | Sí |
| PRECIO | Precio de la línea, con el formato del PDF | No (casilla «Mostrar precio») |
| PRECIO -N% | PRECIO menos N % (0–100, por defecto 40), mismo formato | No (casilla «Mostrar precio con descuento») |

- Una fila por línea del PDF: **no se suman** cantidades de códigos repetidos.
- Las columnas vacías se mantienen al copiar para que los valores caigan en su columna.

### 3.5 Botones
- **Organizar listado**: orden alfanumérico natural (A2 < A10). Mueve filas completas, así cada código conserva su cantidad y precios. No se aplica solo.
- **Copiar Resultado**: copia lo que se ve, en el orden mostrado (original del PDF u organizado), sin encabezados, separado por tabulaciones. Las columnas ocultas no se copian.

---

## 4. Cómo lee el PDF

1. Junta **todas las páginas en una sola lista de líneas**, en orden, para que los saltos de página no corten artículos.
2. Empieza a buscar artículos **después de la línea «N artículos»** (si existe), para no confundir notas del cliente del encabezado con referencias, y **termina en «Total»** (lo de abajo es pie).
3. Arma cada artículo con tres piezas: **cantidad** (`5x`), **código** y **precio** (`$…`). Reconoce estos formatos:
   - todo en una línea: `5x 674B-1 POEDAGAR … $430,000.00`;
   - código arriba y cantidad + precio debajo (descripción larga en varias líneas);
   - cantidad y precio al final de una página y el código al inicio de la siguiente (o al revés).
4. Un código sin cantidad delante debe tener un dígito y una letra o guion (`810-C1`, `312-1`, `A10`), para no tomar números sueltos como referencias.
5. Si la página tiene encabezados de columna (PRECIO, P.UNIT, V.UNIT…), el precio se toma de esa columna; si no, del valor con `$`.
6. Lo que no se puede completar se reporta en **Revisión** en lugar de incluirse.

Formatos de precio aceptados: `$72,000.00`, `$1.000,50`, `3.200`, `$100`. El precio con descuento conserva el símbolo, el separador de miles y los decimales del original.

---

## 5. Limitaciones conocidas

- Pensado para recibos con el formato «cantidad x código … $precio» (como los de KINO COMPANY). Otros formatos pueden necesitar ajustes.
- Una línea de descripción que empiece con algo parecido a un código (ej. «18K-GOLD») genera un aviso de más; no afecta el listado.
- Si a una cantidad le falta su código y justo después viene otra referencia partida en varias líneas, puede emparejarse mal; la Revisión lo mostrará como descuadre.
- El cliente sin etiqueta «Cliente:» se deduce por la negrita del encabezado; en otros formatos puede quedar vacío.
- PDFs escaneados (imagen, sin texto) no se pueden leer.

---

## 6. Estructura técnica

| Archivo | Función |
|---|---|
| `app.py` | Servidor Flask. `leer_articulos` (lectura continua, avisos, mapa), `datos_pedido` (pedido, cliente, fecha, totales), `leer_precio` / `formatear_precio` (formatos de precio). |
| `templates/index.html` | Página: carga del PDF, Revisión, Datos del pedido, Mapa, tabla y controles. |
| `static/js/main.js` | Organizar, copiar, mostrar/ocultar PRECIO, columna de descuento. |
| `static/css/style.css` | Estilos. |
| `requirements.txt`, `Procfile`, `runtime.txt` | Dependencias y arranque (`gunicorn app:app`). |

Para ejecutarlo en local y desplegarlo, ver `README.md`.
