"""將 research/results/*.json 彙整為 report.md。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parent
RESULTS = ROOT / "results"
FIELDS_YAML = ROOT / "fields.yaml"
OUTLINE_YAML = ROOT / "outline.yaml"
REPORT = ROOT / "report.md"

TOC_FIELDS = ["item_type", "year", "integration_difficulty"]

CATEGORY_MAPPING = {
    "basic_info": ["basic_info", "Basic Info", "基本資訊"],
    "method": ["method", "Method", "方法"],
    "evaluation": ["evaluation", "Evaluation", "評估"],
    "explainability": ["explainability", "Explainability", "可解釋性"],
    "practicality": ["practicality", "Practicality", "實用性"],
    "smelens_relevance": ["smelens_relevance", "ChainLens Relevance", "smelens"],
    "meta": ["meta", "Meta", "來源"],
}

INTERNAL_KEYS = {"_source_file", "uncertain"} | {
    alias for aliases in CATEGORY_MAPPING.values() for alias in aliases
}


def load_field_schema() -> dict[str, list[str]]:
    spec = yaml.safe_load(FIELDS_YAML.read_text(encoding="utf-8"))
    schema: dict[str, list[str]] = {}
    for category, fields in spec.get("fields", {}).items():
        schema[category] = [f["name"] for f in fields]
    return schema


def find_field(data: dict, category: str, field: str):
    """查找順序:頂層 -> category 對應 key -> 走訪所有巢狀 dict。"""
    if field in data:
        return data[field]
    for alias in CATEGORY_MAPPING.get(category, [category]):
        sub = data.get(alias)
        if isinstance(sub, dict) and field in sub:
            return sub[field]
    for value in data.values():
        if isinstance(value, dict) and field in value:
            return value[field]
    return None


def is_uncertain(value, field: str, uncertain_list: list[str]) -> bool:
    if field in uncertain_list:
        return True
    if value is None or value == "" or value == []:
        return True
    return "[uncertain]" in json.dumps(value, ensure_ascii=False)


def fmt(value) -> str:
    if isinstance(value, dict):
        return "; ".join(f"{k}: {fmt(v)}" for k, v in value.items())
    if isinstance(value, list):
        if all(isinstance(x, dict) for x in value) and value:
            return "<br>".join(" | ".join(f"{k}: {fmt(v)}" for k, v in x.items()) for x in value)
        joined = ", ".join(str(x) for x in value)
        return joined if len(joined) <= 150 else "<br>".join(str(x) for x in value)
    text = str(value).strip()
    if len(text) > 100:
        return text.replace("\n", "<br>")
    return text.replace("\n", " ")


def slugify_anchor(name: str) -> str:
    anchor = name.lower()
    anchor = re.sub(r"[^\w\s-]", "", anchor)
    return re.sub(r"[\s]+", "-", anchor).strip("-")


def main() -> None:
    schema = load_field_schema()
    outline = yaml.safe_load(OUTLINE_YAML.read_text(encoding="utf-8"))
    topic = outline.get("topic", "Research Report")

    entries = []
    for path in sorted(RESULTS.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        uncertain = data.get("uncertain", []) or []
        name = find_field(data, "basic_info", "name") or path.stem
        entries.append((str(name), data, uncertain))

    lines = [f"# {topic} — 深度研究報告", "", f"共 {len(entries)} 個研究項目。", "", "## 目錄", ""]
    for i, (name, data, uncertain) in enumerate(entries, 1):
        summary = []
        for field in TOC_FIELDS:
            value = find_field(data, "basic_info", field) or find_field(data, "practicality", field)
            if value is not None and not is_uncertain(value, field, uncertain):
                summary.append(f"{field}: {fmt(value)[:60]}")
        suffix = f" — {' | '.join(summary)}" if summary else ""
        lines.append(f"{i}. [{name}](#{slugify_anchor(name)}){suffix}")
    lines.append("")

    for name, data, uncertain in entries:
        lines += [f"## {name}", ""]
        for category, fields in schema.items():
            rows = []
            for field in fields:
                value = find_field(data, category, field)
                if is_uncertain(value, field, uncertain):
                    continue
                rows.append(f"- **{field}**: {fmt(value)}")
            if rows:
                lines += [f"### {category}", "", *rows, ""]
        extras = {
            k: v
            for k, v in data.items()
            if k not in INTERNAL_KEYS and not isinstance(v, dict)
            and not any(k in fs for fs in schema.values())
        }
        if extras:
            lines += ["### other_info", ""]
            lines += [f"- **{k}**: {fmt(v)}" for k, v in extras.items()]
            lines.append("")
        if uncertain:
            lines += ["### uncertain fields", ""]
            lines += [f"- {u}" for u in uncertain]
            lines.append("")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"report written: {REPORT} ({len(entries)} items)")


if __name__ == "__main__":
    main()
