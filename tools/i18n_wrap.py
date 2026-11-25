"""עוטף כל טקסט עברי בקוד ב-tx(...) כדי שיתורגם לפי השפה, ומייצר את קובצי השפה.
הרצה:  python tools/i18n_wrap.py          - עוטף טקסטים חדשים ומעדכן את shir_studio/lang/he.json
        python tools/i18n_wrap.py --check  - רק מדווח מה חסר בקובצי התרגום"""
import ast
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shir_studio")
SKIP = {"i18n.py", "ed25519.py", "license_key.py", "_version.py"}
HEB = re.compile("[֐-׿]")


def has_heb(s):
    return isinstance(s, str) and bool(HEB.search(s))


class Finder(ast.NodeVisitor):
    def __init__(self):
        self.jobs = []          # (node, kind)
        self.problems = []
        self.keys = []

    def visit_Expr(self, node):
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return                                   # docstring
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id == "tx":
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                self.keys.append(node.args[0].value)
            return                                   # כבר עטוף
        self.generic_visit(node)

    def visit_Constant(self, node):
        if has_heb(node.value):
            self.jobs.append((node, "const"))

    def visit_JoinedStr(self, node):
        parts = [v for v in node.values if isinstance(v, ast.Constant)]
        inner = [n for v in node.values if isinstance(v, ast.FormattedValue)
                 for n in ast.walk(v.value) if isinstance(n, ast.Constant) and has_heb(n.value)]
        if inner:
            self.problems.append((node.lineno, "עברית בתוך ביטוי של f-string"))
            return
        if any(has_heb(p.value) for p in parts):
            self.jobs.append((node, "fstr"))


def fstring_to_format(node):
    tmpl, args = "", []
    for v in node.values:
        if isinstance(v, ast.Constant):
            tmpl += v.value.replace("{", "{{").replace("}", "}}")
        else:
            spec = ""
            if v.format_spec is not None:
                if not all(isinstance(x, ast.Constant) for x in v.format_spec.values):
                    return None
                spec = ":" + "".join(x.value for x in v.format_spec.values)
            conv = {-1: "", 115: "!s", 114: "!r", 97: "!a"}[v.conversion]
            tmpl += "{" + str(len(args)) + conv + spec + "}"
            args.append(ast.unparse(v.value))
    return tmpl, args


def lit(s):
    return json.dumps(s, ensure_ascii=False)


def process(path, write=True):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    f = Finder()
    f.visit(tree)
    lines = src.split("\n")
    starts = []
    off = 0
    for ln in lines:
        starts.append(off)
        off += len(ln.encode("utf-8")) + 1
    data = src.encode("utf-8")
    edits = []
    for node, kind in f.jobs:
        a = starts[node.lineno - 1] + node.col_offset
        b = starts[node.end_lineno - 1] + node.end_col_offset
        seg = data[a:b].decode("utf-8")
        if kind == "const":
            new = "tx(" + seg + ")"
            f.keys.append(node.value)
        else:
            r = fstring_to_format(node)
            if r is None:
                f.problems.append((node.lineno, "f-string מורכב"))
                continue
            tmpl, args = r
            new = "tx(" + lit(tmpl) + ")" + (".format(" + ", ".join(args) + ")" if args else "")
            f.keys.append(tmpl)
        edits.append((a, b, new))
    if edits and write:
        for a, b, new in sorted(edits, reverse=True):
            data = data[:a] + new.encode("utf-8") + data[b:]
        out = data.decode("utf-8")
        if not re.search(r"^from \.+i18n import tx", out, re.M):
            depth = os.path.relpath(path, ROOT).count(os.sep) + 1
            imp = "from " + "." * depth + "i18n import tx"
            ls = out.split("\n")
            t2 = ast.parse(out)
            first = next((n for n in t2.body if isinstance(n, (ast.Import, ast.ImportFrom))
                          and not (isinstance(n, ast.ImportFrom) and n.module == "__future__")), None)
            at = (first.lineno - 1) if first else 0
            ls.insert(at, imp)
            out = "\n".join(ls)
        ast.parse(out)
        open(path, "w", encoding="utf-8").write(out)
    return f.keys, f.problems


def style_keys():
    keys = []
    d = os.path.join(ROOT, "styles")
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".json"):
            s = json.load(open(os.path.join(d, fn), encoding="utf-8"))
            keys += [s.get("name", ""), s.get("description", "")]
    return [k for k in keys if k]


def main():
    check = "--check" in sys.argv
    keys, problems = [], []
    for base, _dirs, files in os.walk(ROOT):
        for fn in sorted(files):
            if fn.endswith(".py") and fn not in SKIP:
                p = os.path.join(base, fn)
                k, pr = process(p, write=not check)
                if not check:                         # אחרי העטיפה - אוספים את המפתחות מהקובץ המעודכן
                    k, _pr = process(p, write=False)
                keys += k
                problems += [(os.path.relpath(p, ROOT), ln, why) for ln, why in pr]
    keys += style_keys()
    seen = list(dict.fromkeys(keys))
    lang_dir = os.path.join(ROOT, "lang")
    os.makedirs(lang_dir, exist_ok=True)
    if not check:
        json.dump({k: k for k in seen}, open(os.path.join(lang_dir, "he.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=0)
    print(len(seen), "טקסטים")
    for code in ("en", "yi"):
        p = os.path.join(lang_dir, code + ".json")
        have = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
        missing = [k for k in seen if not have.get(k)]
        print(code, "- חסרים", len(missing))
        if "--missing" in sys.argv:
            json.dump({k: "" for k in missing}, open(os.path.join(lang_dir, code + ".missing.json"), "w",
                                                     encoding="utf-8"), ensure_ascii=False, indent=0)
    for pr in problems:
        print("לטיפול ידני:", *pr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
