"""Guard against research Modal startup imports from unrelated live apps."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "modal_whisper_word_timing_audit.py"
BASELINE = ROOT / "beta_modal_anonymous.py"


def image_expr(path, name):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.unparse(node.value)
    raise AssertionError(f"Missing {name} image builder")


class WhisperAuditImageStartupTests(unittest.TestCase):
    def test_audit_does_not_import_another_modal_app_at_startup(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        imports = [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        ] + [
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        ]
        self.assertNotIn("beta_modal_anonymous", imports)
        self.assertNotIn("beta_modal", imports)

    def test_audit_preserves_frozen_gpu_dependencies(self):
        audit = image_expr(SOURCE, "image")
        baseline = image_expr(BASELINE, "gpu_image")
        # Only the mounted Python source package set is permitted to differ.
        audit_common = audit.replace("'scripts', 'transcriber'", "'beta', 'transcriber'")
        self.assertEqual(audit_common, baseline)
        self.assertIn("'scripts', 'transcriber'", audit)
        self.assertNotIn("'beta', 'transcriber'", audit)

    def test_audit_never_deploys_web_app(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("@modal.asgi_app", source)
        self.assertNotIn("@modal.fastapi_endpoint", source)
        self.assertIn("retries=0", source)
        self.assertIn("single_use_containers=True", source)


if __name__ == "__main__":
    unittest.main()
