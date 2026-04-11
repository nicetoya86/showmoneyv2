import json
import re
from pathlib import Path

SRC = Path(r"D:\vibecording\showmoneyv2\Autostock Complete (v2.1 - 09_10 Start) + Blacklist + Holidays2026 (UserDates) + FixedScalpingTheme.json")
OUT = Path(r"D:\vibecording\showmoneyv2\Autostock Complete (v2.1 - 09_10 Start) + Blacklist + Holidays2026 (UserDates) + FixedScalpingTheme + ThemeFilterOff + DebugEnhanced.json")

wf = json.loads(SRC.read_text(encoding="utf-8"))
nodes = wf.get("nodes", [])
if isinstance(nodes, dict):
    nodes = list(nodes.values())


def _inject_theme_mode(code: str, kind: str) -> str:
    # Default OFF; keeps theme cache timestamps for debug but disables exclusion.
    needle = "  const themeSet = new Set((bl.themeCodes || []).map(String));\n"
    if needle not in code:
        raise RuntimeError(f"[{kind}] themeSet needle not found")

    repl = (
        "  const themeFilterMode = String(bl.themeFilterMode || 'off').toLowerCase();\n"
        "  const themeSet = (themeFilterMode === 'off') ? new Set() : new Set((bl.themeCodes || []).map(String));\n"
    )
    return code.replace(needle, repl)


def _inject_yahoo_counters(code: str, kind: str) -> str:
    if "yahooOkCount" in code:
        return code

    insert = (
        "\n  // ===== Debug counters (Yahoo) =====\n"
        "  let yahooOkCount = 0;\n"
        "  let yahooNoResultCount = 0;\n"
        "  let yahooErrorCount = 0;\n"
        "  const yahooErrorByStatus = {};\n"
        "  const yahooErrorSamples = [];\n"
        "  const pickStatus = (e) => {\n"
        "    const s = e?.statusCode ?? e?.response?.statusCode ?? e?.response?.status ?? e?.httpCode ?? e?.cause?.statusCode;\n"
        "    const n = Number(s);\n"
        "    return Number.isFinite(n) ? n : null;\n"
        "  };\n"
        "  // ===== /Debug counters (Yahoo) =====\n\n"
    )

    m = re.search(r"\n\s*const httpIntra\s*=\s*async", code)
    if not m:
        raise RuntimeError(f"[{kind}] httpIntra marker not found")
    # Insert right before the first httpIntra definition
    return code[: m.start() + 1] + insert + code[m.start() + 1 :]


def _count_noresult_ok(code: str, kind: str) -> str:
    # common (scalping)
    needle = "        if (!rIntra || !rDaily) return;\n"
    repl = "        if (!rIntra || !rDaily) { yahooNoResultCount++; return; }\n        yahooOkCount++;\n"
    if needle in code:
        return code.replace(needle, repl)

    # fallback (swing): different indentation/newlines
    code2, _n = re.subn(
        r"\n(?P<indent>\s*)if\s*\(\s*!rIntra\s*\|\|\s*!rDaily\s*\)\s*return;\s*\n",
        lambda m: (
            f"\n{m.group('indent')}if (!rIntra || !rDaily) {{ yahooNoResultCount++; return; }}\n"
            f"{m.group('indent')}yahooOkCount++;\n"
        ),
        code,
        count=1,
    )
    return code2


def _replace_scanloop_silent_catch(code: str, kind: str) -> str:
    # Only replace the silent catch inside the per-ticker scan loop,
    # not other silent catches (e.g., telegram debug send).
    start_token = "batch.map(async (t) => {"
    start = code.find(start_token)
    if start < 0:
        raise RuntimeError(f"[{kind}] scan loop start not found")

    # Find the scan-loop's silent catch after start_token
    needles = ["      } catch (e) {}", "        } catch (e) {}"]
    pos = -1
    needle = None
    for s in needles:
        p = code.find(s, start)
        if p >= 0 and (pos < 0 or p < pos):
            pos = p
            needle = s

    if pos < 0 or needle is None:
        raise RuntimeError(f"[{kind}] scan loop silent catch not found")

    indent = needle.split("}")[0]  # leading spaces
    repl = (
        f"{indent}}} catch (e) {{\n"
        f"{indent}  yahooErrorCount++;\n"
        f"{indent}  const st = pickStatus(e);\n"
        f"{indent}  const key = String(st || 'ERR');\n"
        f"{indent}  yahooErrorByStatus[key] = (yahooErrorByStatus[key] || 0) + 1;\n"
        f"{indent}  if (yahooErrorSamples.length < 3) {{\n"
        f"{indent}    yahooErrorSamples.push({{ ticker: t, status: st, message: (e?.message || String(e)).slice(0, 180) }});\n"
        f"{indent}  }}\n"
        f"{indent}}}"
    )

    return code[:pos] + repl + code[pos + len(needle):]


def _extend_debug_message_and_return(code: str, kind: str) -> str:
    if kind == "scalping":
        code = code.replace(
            "      `- 제외(테마): ${excludedTheme}개` + NL +\n",
            "      `- 제외(테마): ${excludedTheme}개` + NL +\n"
            "      `- Yahoo OK/NoResult/Error: ${yahooOkCount}/${yahooNoResultCount}/${yahooErrorCount}` + NL +\n"
            "      `- Yahoo err status: ${Object.keys(yahooErrorByStatus).slice(0,4).map(k=>k+':'+yahooErrorByStatus[k]).join(', ') || 'none'}` + NL +\n",
        )
        code = code.replace(
            "      themeCacheAt,\n",
            "      themeCacheAt,\n      yahooOkCount,\n      yahooNoResultCount,\n      yahooErrorCount,\n      yahooErrorByStatus,\n      yahooErrorSamples,\n",
        )
        return code

    # swing no-picks debug message
    code = code.replace(
        "      '- themeCacheAt: ' + (themeCacheAt || 'null') + NL +\n",
        "      '- themeCacheAt: ' + (themeCacheAt || 'null') + NL +\n"
        "      '- Yahoo OK/NoResult/Error: ' + yahooOkCount + '/' + yahooNoResultCount + '/' + yahooErrorCount + NL +\n"
        "      '- Yahoo err status: ' + (Object.keys(yahooErrorByStatus).slice(0,4).map(k=>k+':' + yahooErrorByStatus[k]).join(', ') || 'none') + NL +\n",
    )

    code = code.replace(
        "        themeCacheAt,\n",
        "        themeCacheAt,\n        yahooOkCount,\n        yahooNoResultCount,\n        yahooErrorCount,\n        yahooErrorByStatus,\n        yahooErrorSamples,\n",
    )
    return code


def transform(code: str, kind: str) -> str:
    before = code
    code = _inject_theme_mode(code, kind)
    code = _inject_yahoo_counters(code, kind)
    code = _count_noresult_ok(code, kind)
    code = _replace_scanloop_silent_catch(code, kind)
    code = _extend_debug_message_and_return(code, kind)

    if code == before:
        raise RuntimeError(f"[{kind}] no changes applied")
    if "themeFilterMode" not in code:
        raise RuntimeError(f"[{kind}] themeFilterMode missing")
    if "yahooOkCount" not in code:
        raise RuntimeError(f"[{kind}] yahooOkCount missing")

    return code


updated = []
for n in nodes:
    name = n.get("name")
    if name in ("Scalping Scanner", "Swing Scanner"):
        fc = ((n.get("parameters") or {}).get("functionCode")) or ""
        kind = "scalping" if name == "Scalping Scanner" else "swing"
        n.setdefault("parameters", {})["functionCode"] = transform(fc, kind)
        updated.append(name)

if set(updated) != {"Scalping Scanner", "Swing Scanner"}:
    raise RuntimeError("Could not update both scanners: " + str(updated))

OUT.write_text(json.dumps(wf, ensure_ascii=False), encoding="utf-8")
print("OK wrote:", OUT)
