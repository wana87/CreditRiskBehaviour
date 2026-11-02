"""Execute the supplied profiler YAML pipeline without changing its formulas."""
from datetime import datetime, timezone
from pathlib import Path
import json
import math
import re

import yaml
from lupa.lua54 import LuaRuntime, LuaError, LuaMemoryError

CONFIG_FILES = ("input-mappings.yml", "pre-processing.yml", "feature-encoders.yml",
                "graph.yml", "summary.yml")


class PipelineError(ValueError):
    pass


def load_config(folder):
    config = {}
    for filename in CONFIG_FILES:
        value = yaml.safe_load((Path(folder) / filename).read_text(encoding="utf-8"))
        if not isinstance(value, list) or not all(isinstance(x, dict) for x in value):
            raise PipelineError(f"{filename}: expected a list of mappings")
        config[filename] = value
    return config


def lookup(data, path):
    """Support the supplied $.a.b and $.facilities..a..b path dialect.

    Array projections retain missing leaf values to keep parallel arrays aligned.
    This is deliberately a small dialect, not a complete JSONPath implementation.
    """
    if not isinstance(path, str) or not path.startswith("$."):
        raise PipelineError(f"Unsupported path: {path!r}")
    if path.startswith("$.features."):
        key = path[len("$.features."):]
        if key.startswith("['") and key.endswith("']"):
            key = key[2:-2]
        return data.get("features", {}).get(key)
    if not re.fullmatch(r"\$\.[A-Za-z_][\w.]*(?:[\w])?", path):
        raise PipelineError(f"Unsupported path: {path}")
    parts = path[2:].replace("..", ".").split(".")
    array_keys = set(re.findall(r"(\w+)\.\.", path))

    def walk(value, remaining):
        if not remaining:
            return [value]
        if isinstance(value, list):
            return [leaf for item in value for leaf in walk(item, remaining)]
        child = value.get(remaining[0]) if isinstance(value, dict) else None
        if remaining[0] in array_keys:
            if child is None:
                child = []
            if not isinstance(child, list):
                raise PipelineError(f"{remaining[0]} must be an array.")
        return walk(child, remaining[1:])

    values = walk(data, parts)
    return values if ".." in path else (values[0] if values else None)


def parse_records(text):
    if len(text.encode("utf-8")) > 5_000_000:
        raise PipelineError("Input exceeds the 5 MB limit.")
    text = text.strip()
    if not text:
        raise PipelineError("Provide at least one JSON report.")
    try:
        if text.startswith("["):
            records = json.loads(text)
        else:
            try:
                records = [json.loads(text)]
            except json.JSONDecodeError:
                records = []
                for line_no, line in enumerate(text.splitlines(), 1):
                    if line.strip():
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError as exc:
                            raise PipelineError(f"Invalid JSON on line {line_no}: {exc.msg}") from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(f"Invalid JSON: {exc.msg}") from exc
    if not isinstance(records, list) or not 1 <= len(records) <= 100:
        raise PipelineError("Provide between 1 and 100 reports.")
    if not all(isinstance(record, dict) for record in records):
        raise PipelineError("Each report must be a JSON object.")
    return records


def _number(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise PipelineError("Boolean supplied for a NUMBER field.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise PipelineError(f"Expected a number, received {value!r}") from exc
    if not math.isfinite(result):
        raise PipelineError("Numbers must be finite.")
    return int(result) if result.is_integer() else result


class Expressions:
    """A fresh Lua 5.4 runtime per report; no Python, file or OS APIs exposed."""
    def __init__(self):
        self.lua = LuaRuntime(register_eval=False, register_builtins=False,
                              max_memory=16 * 1024 * 1024)
        self.array = self.lua.eval("""function(t, n)
            return setmetatable(t, {__len=function() return n end}) end""")
        self.run = self.lua.eval("""function(source, inputs)
            local env = {inputs=inputs, outputs={}, tonumber=tonumber,
                string={sub=string.sub, len=string.len}}
            local fn, err = load(source, 'feature', 't', env)
            if not fn then error(err) end
            local ticks = 0
            debug.sethook(function()
                ticks = ticks + 1
                if ticks > 2000 then error('Expression instruction limit exceeded') end
            end, '', 1000)
            local ok, message = pcall(fn)
            debug.sethook()
            if not ok then error(message) end
            return env.outputs[1]
        end""")

    def convert(self, value):
        if isinstance(value, list):
            table = self.lua.table()
            for index, item in enumerate(value, 1):
                table[index] = self.convert(item)
            return self.array(table, len(value))
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise PipelineError("Expression inputs must be scalar values or arrays.")
        return value

    def evaluate(self, expression, values):
        source = re.sub(r"\bin\.\$(\d+)", r"inputs[\1]", expression)
        source = re.sub(r"\bout\.\$(\d+)", r"outputs[\1]", source)
        result = self.run(source, self.convert(values))
        if result is not None and not isinstance(result, (str, int, float, bool)):
            raise PipelineError("Expression must return a scalar value.")
        if isinstance(result, float) and not math.isfinite(result):
            return None
        return result


def profile(record, config, now=None):
    if not isinstance(record, dict):
        raise PipelineError("Report must be a JSON object.")
    for key in ("transaction", "borrower", "report"):
        if key in record and not isinstance(record[key], dict):
            raise PipelineError(f"{key} must be an object.")
    facilities = record.get("facilities") or []
    if not isinstance(facilities, list):
        raise PipelineError("facilities must be an array.")
    for facility in facilities:
        if not isinstance(facility, dict):
            raise PipelineError("Each facility must be an object.")
        for key in ("latest_position", "reporting_institution"):
            if facility.get(key) is not None and not isinstance(facility[key], dict):
                raise PipelineError(f"{key} must be an object.")
        history = facility.get("payment_history_24m") or []
        if not isinstance(history, list) or not all(isinstance(x, dict) for x in history):
            raise PipelineError("payment_history_24m must be an array of objects.")
    now = now or datetime.now(timezone.utc)
    features = {"_today": now.isoformat().replace("+00:00", "Z"),
                "_query_id": record.get("_query_id") or record.get("transaction", {}).get("id")}
    for mapping in config["input-mappings.yml"]:
        name = mapping["output"]
        value = lookup(record, mapping["input"])
        if mapping.get("required") and (value is None or value == "" or value == []):
            raise PipelineError(f"Missing required field: {mapping['input']}")
        converter = _number if mapping.get("type") == "NUMBER" else lambda x: None if x is None else str(x)
        features[name] = [converter(x) for x in value] if isinstance(value, list) else converter(value)
    period = features.get("report.analysis_period", "")
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
        raise PipelineError("analysis_reporting_period must use YYYY-MM with a valid month.")
    runtime = Expressions()
    for filename in ("pre-processing.yml", "feature-encoders.yml"):
        for spec in config[filename]:
            output = spec["output"]
            keys = spec["input"] if isinstance(spec["input"], list) else [spec["input"]]
            values = [features.get(key) for key in keys]
            encoding = spec["encoding"]
            try:
                if encoding["type"] == "expression-encoding":
                    result = runtime.evaluate(encoding["expression"], values)
                elif encoding["type"] == "date-conversion-encoding":
                    if (encoding.get("input-format"), encoding.get("output-format")) != ("ISO_8601", "UNIX_TIMESTAMP_MILLIS"):
                        raise PipelineError("Unsupported date conversion formats.")
                    dt = datetime.fromisoformat(values[0].replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    result = int(dt.timestamp() * 1000)
                else:
                    raise PipelineError(f"Unsupported encoding: {encoding['type']}")
            except (LuaError, LuaMemoryError, ValueError, TypeError, AttributeError) as exc:
                raise PipelineError(f"{filename} / {output}: {exc}") from exc
            if result is None and spec.get("default-value") not in (None, "<NaN>"):
                result = spec["default-value"]
            features[output] = result
    vertices, edges = [], []
    for spec in config["graph.yml"]:
        properties = {p["key"]: features.get(p["value"]) for p in spec.get("properties", [])}
        node = {"label": spec["label"], "properties": properties}
        if spec["type"] == "vertex":
            node["ids"] = [features.get(key) for key in spec["ids"]]
            vertices.append(node)
        elif spec["type"] == "edge":
            node["from_ids"] = [features.get(key) for key in spec["from_vertex_ids"]]
            node["to_ids"] = [features.get(key) for key in spec["to_vertex_ids"]]
            edges.append(node)
        else:
            raise PipelineError(f"Unsupported graph element: {spec['type']}")
    visible = dict(features)
    for spec in config["pre-processing.yml"] + config["feature-encoders.yml"]:
        if spec.get("visible") is False:
            visible.pop(spec["output"], None)
    visible = {key: value for key, value in visible.items() if not key.startswith("_")}
    result = {"features": visible, "graph": {"vertices": vertices, "edges": edges}}
    result["summary"] = [{"label": item["label"], "value": lookup(result, item["path"])}
                         for item in config["summary.yml"]]
    return result
