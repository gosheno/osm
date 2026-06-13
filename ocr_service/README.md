# OCR Service

FastAPI microservice for extracting route/address rows from table screenshots.

## Endpoints

- `GET /health`
- `POST /api/ocr/route-table`
- `POST /api/ocr/text`
- `POST /api/ocr/debug-table`
- `POST /ocr` legacy plain-text compatibility endpoint

`/api/ocr/route-table` accepts multipart form fields:

- `file`
- `engine`: `auto`, `paddle`, `tesseract`, `native_paddle`
- `lang`: default `ru`
- `cell_mode`: `raw`, `gray`, `binary`, `auto`
- `line_mode`: `soft`, `aggressive`
- `debug`: `true` or `false`
- `extract_addresses`: `true` or `false`

## Default Flow

Image upload -> validation -> OpenCV resize/perspective/preprocess -> table line detection -> cell segmentation -> PaddleOCR per-cell recognition -> Tesseract fallback -> row normalization -> conservative address extraction -> JSON response.

Debug mode returns base64 PNG artifacts for the perspective-corrected image, grid masks, table crop, detected cells, and recognized cell overlay.

## Environment

```text
OCR_DEFAULT_ENGINE=auto
OCR_DEFAULT_LANG=ru
OCR_FALLBACK_LANG=cyrillic
OCR_MAX_FILE_SIZE_MB=10
OCR_MAX_IMAGE_SIDE=4000
OCR_DEBUG_ARTIFACT_TTL_MINUTES=60
OCR_ENABLE_DEBUG_ARTIFACTS=true
PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT=0
```

## Run

```bash
docker compose up --build ocr
```

Then check:

```bash
curl http://localhost:8088/health
```

## Test

```bash
pip install -r requirements.txt -r requirements-dev.txt
PYTHONPATH=. pytest
```

Paddle package pins are explicit in `requirements.txt`; rebuild the Docker image after changing them because Paddle CPU wheels are sensitive to Python and platform versions.
