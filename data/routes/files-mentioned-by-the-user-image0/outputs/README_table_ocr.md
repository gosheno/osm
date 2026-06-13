# OCR таблицы с фото

Файлы:

- `table_ocr_tesseract_opencv.py` - основной скрипт.
- `requirements_ocr.txt` - Python-зависимости.

Установка Python-зависимостей:

```powershell
python -m pip install -r requirements_ocr.txt
```

Также нужен установленный Tesseract OCR с русским языком `rus`.
Если `tesseract.exe` не добавлен в `PATH`, передайте путь через `--tesseract-cmd`.

Пример запуска:

```powershell
python table_ocr_tesseract_opencv.py `
  --image "C:\Gosha\python\OSM ROUTES\osm-route-mvp\data\routes\route22\image0.jpg" `
  --output-dir ".\ocr_result" `
  --lang rus+eng `
  --cell-mode gray `
  --tesseract-cmd "C:\Program Files\Tesseract-OCR\tesseract.exe" `
  --show
```

Сначала можно проверить только детекцию таблицы без OCR:

```powershell
python table_ocr_tesseract_opencv.py `
  --image "C:\Gosha\python\OSM ROUTES\osm-route-mvp\data\routes\route22\image0.jpg" `
  --output-dir ".\ocr_debug" `
  --skip-ocr `
  --show
```

Результат:

- `ocr_table.csv` - таблица с разделителем `;`.
- `ocr_table.tsv` - таблица с tab-разделителем.
- `ocr_table.xlsx` - Excel-файл, если установлен `pandas/openpyxl`.
- `ocr_table.html` - HTML-таблица, если установлен `pandas`.
- `debug/*.png` - все этапы предобработки и разметки ячеек.

Если линии таблицы находятся плохо, попробуйте менять:

```powershell
--horizontal-scale 45 --vertical-scale 45
```

Чем больше значение scale, тем короче линии может поймать OpenCV.

Если OCR плохо читает конкретные ячейки, можно попробовать:

```powershell
--cell-mode auto
```

или более агрессивный режим:

```powershell
--cell-mode binary
```

По умолчанию используется `--cell-mode gray`: он сохраняет качество текста лучше,
чем жесткая бинаризация.
