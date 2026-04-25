from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

import pandas as pd
from pydantic import create_model

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from llm import LLMConfig, PydanticAIChatClient, get_env_value, load_env_file


FEISHU_DOCS_DIR = ROOT_DIR / "docs" / "feishu"
ENV_VALUES = load_env_file(ROOT_DIR / ".env")
EXCEL_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@dataclass(frozen=True, slots=True)
class PromptSheetConfig:
    sheet_name: str
    prompt_column: str
    date_column: str | None
    prompt_file: pathlib.Path
    output_csv: pathlib.Path
    output_json: pathlib.Path
    log_file: pathlib.Path
    expected_fields: list[str]


def configure_logging(log_file: pathlib.Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )


def read_shared_strings(zip_file: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zip_file.namelist():
        return []
    root = ET.fromstring(zip_file.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root.findall("a:si", EXCEL_NS):
        values.append("".join(node.text or "" for node in item.iterfind(".//a:t", EXCEL_NS)))
    return values


def column_index_from_ref(cell_ref: str) -> int:
    letters = "".join(char for char in cell_ref if char.isalpha())
    value = 0
    for char in letters:
        value = value * 26 + (ord(char.upper()) - ord("A") + 1)
    return value - 1


def resolve_sheet_path(xlsx_path: pathlib.Path, sheet_name: str) -> str:
    with zipfile.ZipFile(xlsx_path) as zip_file:
        workbook = ET.fromstring(zip_file.read("xl/workbook.xml"))
        rels = ET.fromstring(zip_file.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
        for sheet in workbook.iter():
            if sheet.tag.endswith("sheet") and sheet.attrib.get("name") == sheet_name:
                rel_id = sheet.attrib[
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                ]
                return "xl/" + rel_map[rel_id]
    raise ValueError(f"Cannot find sheet: {sheet_name}")


def read_sheet_rows(xlsx_path: pathlib.Path, sheet_path: str) -> list[list[str]]:
    with zipfile.ZipFile(xlsx_path) as zip_file:
        shared_strings = read_shared_strings(zip_file)
        root = ET.fromstring(zip_file.read(sheet_path))
        rows: list[list[str]] = []
        for row in root.findall(".//a:sheetData/a:row", EXCEL_NS):
            indexed_values: dict[int, str] = {}
            max_index = -1
            for cell in row.findall("a:c", EXCEL_NS):
                cell_ref = cell.attrib.get("r", "")
                cell_index = column_index_from_ref(cell_ref) if cell_ref else max_index + 1
                max_index = max(max_index, cell_index)

                cell_type = cell.attrib.get("t")
                value_node = cell.find("a:v", EXCEL_NS)
                value = ""
                if cell_type == "s" and value_node is not None and value_node.text is not None:
                    value = shared_strings[int(value_node.text)]
                elif cell_type == "inlineStr":
                    value = "".join(node.text or "" for node in cell.iterfind(".//a:t", EXCEL_NS))
                elif value_node is not None and value_node.text is not None:
                    value = value_node.text
                indexed_values[cell_index] = value

            if max_index < 0:
                rows.append([])
                continue
            rows.append([indexed_values.get(index, "") for index in range(max_index + 1)])
        return rows


def load_prompt_dataframe(xlsx_path: pathlib.Path, sheet_name: str) -> pd.DataFrame:
    sheet_path = resolve_sheet_path(xlsx_path, sheet_name)
    rows = read_sheet_rows(xlsx_path, sheet_path)
    if not rows:
        raise ValueError(f"Sheet is empty: {sheet_name}")

    header = rows[0]
    data_rows = rows[1:]
    normalized_rows = [row + [""] * (len(header) - len(row)) for row in data_rows]
    df = pd.DataFrame(normalized_rows, columns=header)
    return df[df.apply(lambda row: any(str(value).strip() for value in row.tolist()), axis=1)].reset_index(
        drop=True
    )


def detect_column(df: pd.DataFrame, candidates: list[str], label: str) -> str | None:
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    if label == "date":
        return None
    raise ValueError(f"Cannot find {label} column. Available columns: {list(df.columns)}")


def build_batch_system_prompt(instruction_text: str, expected_fields: list[str]) -> str:
    return (
        instruction_text.strip()
        + "\n\n"
        + "Return one JSON object only with a top-level field named results."
        + " results must be an array."
        + " Each item must contain exactly these fields: row_index, "
        + ", ".join(expected_fields)
        + ". Use the provided row_index unchanged."
        + " Every input row must produce exactly one output item."
        + " Use empty strings for missing fields. Do not return markdown."
    )


def build_batch_user_prompt(records: list[dict[str, str | int | None]]) -> str:
    return (
        "Parse every prompt below and return structured results for all rows.\n\n"
        + "Input rows JSON:\n"
        + json.dumps(records, ensure_ascii=False, indent=2)
    )


def normalize_field_value(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(item).strip() for item in value if str(item).strip())
    if value is None:
        return ""
    return str(value).strip()


def build_output_models(expected_fields: list[str]) -> tuple[type[Any], type[Any]]:
    item_fields: dict[str, tuple[type[Any], Any]] = {"row_index": (int, ...)}
    for field in expected_fields:
        item_fields[field] = (str, "")
    row_model = create_model("ParsedPromptRow", **item_fields)
    wrapper_model = create_model("ParsedPromptBatch", results=(list[row_model], ...))
    return row_model, wrapper_model


def parse_prompts_batch(
    *,
    df: pd.DataFrame,
    prompt_column: str,
    date_column: str | None,
    instruction_text: str,
    expected_fields: list[str],
    client: PydanticAIChatClient,
    max_rows: int | None,
) -> pd.DataFrame:
    source_df = df if max_rows is None else df.head(max_rows)
    records: list[dict[str, str | int | None]] = []
    source_rows: dict[int, dict[str, Any]] = {}

    for index, row in source_df.iterrows():
        row_index = index + 2
        source_prompt = str(row.get(prompt_column, "")).strip()
        if not source_prompt:
            logging.info("Skip empty prompt at row %s", row_index)
            continue

        source_record: dict[str, Any] = {
            "row_index": row_index,
            "source_prompt": source_prompt,
        }
        if date_column:
            source_record["updated_at"] = row.get(date_column)
        source_rows[row_index] = source_record

        prompt_record: dict[str, str | int | None] = {
            "row_index": row_index,
            "prompt": source_prompt,
        }
        if date_column:
            prompt_record["updated_at"] = normalize_field_value(row.get(date_column))
        records.append(prompt_record)

    if not records:
        return pd.DataFrame()

    logging.info("Submitting %s prompts in one batch request", len(records))
    _, output_model = build_output_models(expected_fields)
    system_prompt = build_batch_system_prompt(instruction_text, expected_fields)
    user_prompt = build_batch_user_prompt(records)
    logging.info("System prompt sent to model:\n%s", system_prompt)
    logging.info("User prompt sent to model:\n%s", user_prompt)
    payload = client.chat_structured(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        output_type=output_model,
    )

    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise RuntimeError("Model output must contain a top-level results array.")

    parsed_by_row: dict[int, dict[str, str]] = {}
    for item in raw_results:
        if not isinstance(item, dict):
            raise RuntimeError(f"Each results item must be an object, got: {type(item).__name__}")
        row_index = item.get("row_index")
        if not isinstance(row_index, int):
            raise RuntimeError(f"Each results item must have integer row_index, got: {row_index!r}")
        normalized = {field: normalize_field_value(item.get(field, "")) for field in expected_fields}
        parsed_by_row[row_index] = normalized

    missing_rows = [record["row_index"] for record in records if record["row_index"] not in parsed_by_row]
    extra_rows = [row_index for row_index in parsed_by_row if row_index not in source_rows]
    if missing_rows or extra_rows:
        raise RuntimeError(f"Model output row mismatch. missing={missing_rows} extra={extra_rows}")

    results: list[dict[str, Any]] = []
    for record in records:
        row_index = int(record["row_index"])
        result_row = dict(source_rows[row_index])
        result_row.update(parsed_by_row[row_index])
        results.append(result_row)

    return pd.DataFrame(results)


def write_outputs(df: pd.DataFrame, output_csv: pathlib.Path, output_json: pathlib.Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")
    df.to_json(output_json, orient="records", force_ascii=False, indent=2)


def resolve_xlsx_path(raw_path: str) -> pathlib.Path:
    if raw_path:
        return pathlib.Path(raw_path)
    matches = sorted(FEISHU_DOCS_DIR.glob("*.xlsx"))
    if not matches:
        raise FileNotFoundError("No xlsx file found in docs/feishu/.")
    return matches[0]


def build_parser(config: PromptSheetConfig) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse prompts from the Feishu workbook and save structured outputs."
    )
    parser.add_argument(
        "--xlsx",
        default="",
        help="Path to the source xlsx. Defaults to the first xlsx in docs/feishu/.",
    )
    parser.add_argument("--sheet-name", default=config.sheet_name)
    parser.add_argument("--prompt-column", default=config.prompt_column)
    parser.add_argument("--date-column", default=config.date_column or "")
    parser.add_argument("--prompt-file", default=str(config.prompt_file))
    parser.add_argument("--provider", default=get_env_value("LLM_PROVIDER", ENV_VALUES, "gpt"))
    parser.add_argument("--model", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--max-rows", type=int)
    parser.add_argument("--output-csv", default=str(config.output_csv))
    parser.add_argument("--output-json", default=str(config.output_json))
    parser.add_argument("--log-file", default=str(config.log_file))
    return parser


def run_parser(config: PromptSheetConfig, args: argparse.Namespace) -> pd.DataFrame:
    configure_logging(pathlib.Path(args.log_file))

    xlsx_path = resolve_xlsx_path(args.xlsx)
    instruction_text = pathlib.Path(args.prompt_file).read_text(encoding="utf-8")
    source_df = load_prompt_dataframe(xlsx_path, args.sheet_name)
    prompt_column = detect_column(source_df, [args.prompt_column, "prompt"], "prompt")
    date_candidates = [candidate for candidate in [args.date_column, "updated_at"] if candidate]
    date_column = detect_column(source_df, date_candidates, "date")

    logging.info("Loaded %s rows from %s sheet=%s", len(source_df), xlsx_path, args.sheet_name)
    config_llm = LLMConfig.from_env(ENV_VALUES)
    if args.provider:
        config_llm.provider = args.provider.strip().lower()
    if args.model:
        config_llm.model = args.model
    if args.api_key:
        config_llm.api_key = args.api_key
    if args.base_url:
        config_llm.base_url = args.base_url
    if args.timeout:
        config_llm.timeout = args.timeout
    config_llm.validate()

    logging.info(
        "Using provider=%s model=%s base_url=%s",
        config_llm.provider,
        config_llm.model,
        config_llm.resolved_base_url(),
    )
    client = PydanticAIChatClient(config=config_llm)
    parsed_df = parse_prompts_batch(
        df=source_df,
        prompt_column=prompt_column,
        date_column=date_column,
        instruction_text=instruction_text,
        expected_fields=config.expected_fields,
        client=client,
        max_rows=args.max_rows,
    )
    write_outputs(parsed_df, pathlib.Path(args.output_csv), pathlib.Path(args.output_json))
    logging.info("Done. Parsed %s rows", len(parsed_df))
    return parsed_df
