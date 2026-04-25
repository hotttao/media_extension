from __future__ import annotations

import pathlib
import sys

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from feishu.prompt_sheet_parser import FEISHU_DOCS_DIR, PromptSheetConfig, build_parser, run_parser


PROMPT_FILE_NAME = "\u0033\u0032_\u56fe\u751f\u89c6\u9891\u63d0\u793a\u8bcd\u62c6\u89e3.md"
DEFAULT_PROMPT_FILE = ROOT_DIR / "prompts" / PROMPT_FILE_NAME
DEFAULT_OUTPUT_CSV = FEISHU_DOCS_DIR / "\u56fe\u751f\u89c6\u9891\u63d0\u793a\u8bcd\u62c6\u89e3\u7ed3\u679c.csv"
DEFAULT_OUTPUT_JSON = FEISHU_DOCS_DIR / "\u56fe\u751f\u89c6\u9891\u63d0\u793a\u8bcd\u62c6\u89e3\u7ed3\u679c.json"
DEFAULT_LOG_FILE = FEISHU_DOCS_DIR / "\u56fe\u751f\u89c6\u9891\u63d0\u793a\u8bcd\u62c6\u89e3.log"

CONFIG = PromptSheetConfig(
    sheet_name="\u56fe\u751f\u89c6\u9891",
    prompt_column="\u52a8\u6001\u63d0\u793a\u8bcd",
    date_column="\u66f4\u65b0\u65e5\u671f",
    prompt_file=DEFAULT_PROMPT_FILE,
    output_csv=DEFAULT_OUTPUT_CSV,
    output_json=DEFAULT_OUTPUT_JSON,
    log_file=DEFAULT_LOG_FILE,
    expected_fields=[
        "subject",
        "clothing",
        "scene",
        "pose",
        "action",
        "composition",
        "lighting",
        "positive_prompt",
        "negative_prompt",
    ],
)


def main() -> int:
    args = build_parser(CONFIG).parse_args()
    parsed_df = run_parser(CONFIG, args)
    print(f"[DONE] rows={len(parsed_df)} csv={pathlib.Path(args.output_csv)} json={pathlib.Path(args.output_json)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
