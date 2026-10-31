import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class PrivateFourArmContract(unittest.TestCase):
    def test_research_only_cli_and_no_public_gpu_switch(self):
        source=(ROOT/"scripts/run_qwen_fourarm_private.py").read_text()
        ast.parse(source)
        self.assertIn("verified_labels_from_review",source)
        self.assertIn("result=evaluate_four_arms(",source)
        self.assertLess(source.index("result=evaluate_four_arms("),
                        source.index("verified_labels_from_review("))
        self.assertIn("labeling_protocol",source)
        self.assertNotIn("modal.asgi_app()",source)
        beta=(ROOT/"beta_modal.py").read_text()
        self.assertNotIn("run_qwen_fourarm_private",beta)
        self.assertNotIn("qwen_boundary_fourarm",beta)

if __name__=="__main__":
    unittest.main()
