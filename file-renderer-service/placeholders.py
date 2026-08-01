import re

PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


def resolve(path, ctx, warnings):
    """Resolve a dotted path in context dict. Returns empty string if missing."""
    cur = ctx
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            warnings.append(f"missing placeholder value: {path}")
            return ""
    if cur is None:
        return ""
    if isinstance(cur, float) and cur == int(cur):
        cur = int(cur)
    return str(cur)
