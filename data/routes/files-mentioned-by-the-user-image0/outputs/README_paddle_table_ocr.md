# OCR таблицы с фото через PaddleOCR

Файлы:

- `table_ocr_paddle_opencv.py` - OpenCV ищет таблицу и ячейки, PaddleOCR читает текст.
- `native_paddle_table_ocr.py` - встроенный PaddleOCR table pipeline без OpenCV-сетки.
- `requirements_paddleocr.txt` - зависимости Python.

## Установка

PaddlePaddle лучше ставить первым. Для Windows CPU:

```powershell
python -m pip install paddlepaddle -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
```

Затем:

```powershell
python -m pip install "paddleocr[all]" opencv-python numpy pandas openpyxl
```

Проверка:

```powershell
python -c "import paddle; paddle.utils.run_check()"
python -c "from paddleocr import PaddleOCR; print('PaddleOCR OK')"
```

Если pip не найдёт подходящее колесо, открой официальный установщик PaddlePaddle
и выбери свою версию Windows / Python / pip / CPU:

https://www.paddlepaddle.org.cn/en/install/quick

## Запуск

```powershell
python table_ocr_paddle_opencv.py `
  --image "C:\Gosha\python\OSM ROUTES\osm-route-mvp\data\routes\route22\image0.jpg" `
  --output-dir ".\paddle_ocr_result" `
  --lang ru `
  --cell-mode raw `
  --line-mode aggressive `
  --show
```

Скрипт автоматически выставляет:

```powershell
PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT=0
```

Это нужно на CPU, иначе Paddle/PaddleX может падать с ошибкой
`ConvertPirAttribute2RuntimeAttribute`.

Если язык `ru` не поддерживается установленной версией PaddleOCR, попробуй:

```powershell
--lang cyrillic
```

Сначала можно проверить только детекцию таблицы без OCR:

```powershell
python table_ocr_paddle_opencv.py `
  --image "C:\Gosha\python\OSM ROUTES\osm-route-mvp\data\routes\route22\image0.jpg" `
  --output-dir ".\paddle_debug" `
  --skip-ocr `
  --show
```

## Результат

- `ocr_table.csv` - таблица с разделителем `;`.
- `ocr_table.tsv` - таблица с tab-разделителем.
- `ocr_table.xlsx` - Excel-файл.
- `ocr_table.html` - HTML-таблица.
- `debug/*.png` - этапы предобработки, линии таблицы и найденные ячейки.

## Полезные флаги

Мягкое чтение текста:

```powershell
--cell-mode raw
```

Лёгкое усиление текста:

```powershell
--cell-mode gray
```

Автовыбор обработки ячеек:

```powershell
--cell-mode auto
```

Если сетка таблицы плохо находится:

```powershell
--horizontal-scale 45 --vertical-scale 45
```

Если агрессивная маска линий портит детекцию:

```powershell
--line-mode soft
```

## Встроенный Paddle table pipeline

На этой установке PaddleOCR 3.7.0 + PaddlePaddle 3.3.1 на CPU полный
`PaddleOCR.predict()` и `TableRecognitionPipelineV2` работают только если
отключить MKLDNN через:

```powershell
$env:PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT="0"
```

Без этого появляется ошибка:

```text
ConvertPirAttribute2RuntimeAttribute not support [pir::ArrayAttribute<pir::DoubleAttribute>]
```

Проверка встроенного Paddle table pipeline:

```powershell
python native_paddle_table_ocr.py `
  --image "C:\Gosha\python\OSM ROUTES\osm-route-mvp\data\routes\route22\image0.jpg" `
  --output-dir ".\native_paddle_table_result" `
  --lang ru
```

Он сохраняет:

- `paddle_table_1.html`
- `paddle_table_1.csv`
- `paddle_table_1.xlsx`
- `paddle_native_table_result.json`
- `paddle_ocr_fragments.csv`

На коротком фото Paddle сам хорошо читает текст и адреса, но структура таблицы
в `pred_html` всё равно местами переставляет колонки. На длинном фото адреса
тоже читаются, но HTML-таблица получается заметно грязнее.
