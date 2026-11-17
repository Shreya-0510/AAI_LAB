from __future__ import annotations
import ast
from pathlib import Path

EXCLUDED = {".git", ".venv", "venv", "__pycache__", ".tox", "site-packages"}

def analyze_dependencies(repository: str) -> dict:
    root = Path(repository).resolve()
    py_files = [p for p in root.rglob("*.py") if not any(part in EXCLUDED for part in p.parts)]
    module_to_path: dict[str, Path] = {}
    for path in py_files:
        rel = path.relative_to(root).with_suffix("")
        parts = list(rel.parts)
        if parts[-1] == "__init__": parts = parts[:-1]
        module_to_path[".".join(parts)] = path
    edges: list[dict[str, str]] = []
    for source in py_files:
        try: tree = ast.parse(source.read_text(encoding="utf-8", errors="ignore"))
        except (SyntaxError, OSError): continue
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        for module in imports:
            match = module_to_path.get(module)
            if match and match != source:
                edges.append({"source": source.relative_to(root).as_posix(), "target": match.relative_to(root).as_posix(), "import": module})
            else:
                # Resolve simple relative imports by module prefix.
                for candidate, target in module_to_path.items():
                    if candidate.endswith("." + module) and target != source:
                        edges.append({"source": source.relative_to(root).as_posix(), "target": target.relative_to(root).as_posix(), "import": module})
                        break
    return {"edges": edges, "edge_count": len(edges), "node_count": len(py_files), "limitations": "Static AST imports only; dynamic imports and runtime dependencies may be missed."}
