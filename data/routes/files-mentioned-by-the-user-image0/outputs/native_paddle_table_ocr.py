from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from pathlib import Path
from typing import Any


os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "0")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run PaddleOCR native table recognition and save HTML/JSON/CSV."
    )
    parser.add_argument("--image", required=True, help="Path to the source image.")
    parser.add_argument(
        "--output-dir",
        default="native_paddle_table_result",
        help="Directory for Paddle table outputs.",
    )
    parser.add_argument(
        "--lang",
        default="ru",
        help="Language hint. Russian uses eslav_PP-OCRv5_mobile_rec by default.",
    )
    parser.add_argument(
        "--recognition-model",
        default="auto",
        help=(
            "Paddle text recognition model. auto uses eslav_PP-OCRv5_mobile_rec "
            "for --lang ru; pass none to use Paddle default."
        ),
    )
    parser.add_argument(
        "--layout",
        action="store_true",
        help="Enable document layout detection before table recognition.",
    )
    parser.add_argument(
        "--no-ocr",
        action="store_true",
        help="Run table structure only. Usually worse unless OCR is provided.",
    )
    return parser.parse_args()


def model_for_lang(lang: str, recognition_model: str) -> str | None:
    if recognition_model.lower() == "none":
        return None
    if recognition_model != "auto":
        return recognition_model
    if lang.lower() in {"ru", "rus", "russian"}:
        return "eslav_PP-OCRv5_mobile_rec"
    return None


def plain(value: Any) -> Any:
    for attr_name in ("json", "to_dict", "dict"):
        if hasattr(value, attr_name):
            try:
                attr = getattr(value, attr_name)
                return attr() if callable(attr) else attr
            except Exception:
                pass
    if isinstance(value, dict):
        return {
            key: plain(child)
            for key, child in value.items()
            if key not in {"input_img", "vis_font"}
        }
    if isinstance(value, (list, tuple)):
        return [plain(child) for child in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "__dict__"):
        return {
            key: plain(child)
            for key, child in vars(value).items()
            if key not in {"input_img", "vis_font"}
        }
    return repr(value)


def find_pred_html(value: Any) -> list[str]:
    value = plain(value)
    html_fragments: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                if key in {"pred_html", "html"} and isinstance(child, str):
                    html_fragments.append(child)
                else:
                    walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return html_fragments


def find_ocr_texts(value: Any) -> list[tuple[str, float | None]]:
    value = plain(value)
    items: list[tuple[str, float | None]] = []

    def score(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "rec_texts" in node:
                scores = node.get("rec_scores") or []
                for index, text in enumerate(node.get("rec_texts") or []):
                    text = str(text).strip()
                    if text:
                        value = scores[index] if index < len(scores) else None
                        items.append((text, score(value)))
            if "rec_text" in node:
                text = str(node.get("rec_text") or "").strip()
                if text:
                    items.append((text, score(node.get("rec_score"))))
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return items


def write_csv_from_html(html: str, output_dir: Path) -> None:
    try:
        import pandas as pd
    except Exception as exc:
        print(f"pandas is unavailable, CSV from HTML was skipped: {exc}")
        return

    try:
        tables = pd.read_html(io.StringIO(html))
    except Exception as exc:
        print(f"Could not parse Paddle HTML as table: {exc}")
        return

    for index, table in enumerate(tables, 1):
        table.to_csv(
            output_dir / f"paddle_table_{index}.csv",
            index=False,
            header=False,
            sep=";",
            encoding="utf-8-sig",
        )
        try:
            table.to_excel(
                output_dir / f"paddle_table_{index}.xlsx",
                index=False,
                header=False,
            )
        except Exception as exc:
            print(f"Could not write XLSX for table {index}: {exc}")


def main() -> int:
    args = parse_args()
    image = Path(args.image)
    if not image.exists():
        raise SystemExit(f"Image not found: {image}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        from paddleocr import TableRecognitionPipelineV2
    except Exception as exc:
        raise SystemExit(
            "Could not import PaddleOCR. Install paddlepaddle and paddleocr.\n"
            f"Original error: {exc}"
        ) from exc

    recognition_model = model_for_lang(args.lang, args.recognition_model)
    kwargs = {
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_layout_detection": bool(args.layout),
        "use_ocr_model": not args.no_ocr,
    }
    if recognition_model:
        kwargs["text_recognition_model_name"] = recognition_model

    pipeline = TableRecognitionPipelineV2(**kwargs)
    result = pipeline.predict(
        str(image),
        use_layout_detection=bool(args.layout),
        use_ocr_model=not args.no_ocr,
    )
    data = plain(result)

    json_path = output_dir / "paddle_native_table_result.json"
    json_path.write_text(
        json.dumps(data, ensure_ascii=False, default=str, indent=2),
        encoding="utf-8",
    )

    html_fragments = find_pred_html(data)
    for index, html in enumerate(html_fragments, 1):
        html_path = output_dir / f"paddle_table_{index}.html"
        html_path.write_text(html, encoding="utf-8")
        write_csv_from_html(html, output_dir)

    ocr_items = find_ocr_texts(data)
    with (output_dir / "paddle_ocr_fragments.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.writer(file, delimiter=";")
        writer.writerow(["text", "score"])
        writer.writerows(ocr_items)

    print(f"Saved native Paddle result to: {output_dir.resolve()}")
    print(f"HTML tables: {len(html_fragments)}")
    print(f"OCR fragments: {len(ocr_items)}")
    if html_fragments:
        print()
        print(html_fragments[0][:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
