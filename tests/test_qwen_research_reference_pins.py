"""Validate bounded research pins without importing Modal or downloading audio."""
import ast
from pathlib import Path
import unittest


class ResearchReferencePinsTests(unittest.TestCase):
    def test_pins_are_complete_and_match_rechecked_public_references(self):
        tree=ast.parse(Path('modal_qwen_quality_ablation.py').read_text())
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        assignment=next(n for n in main.body if isinstance(n,ast.Assign)
                        and any(isinstance(t,ast.Name) and t.id=='references' for t in n.targets))
        pins=ast.literal_eval(assignment.value)
        self.assertEqual(set(pins),{'01','05','08'})
        for value in pins.values():
            self.assertRegex(value,r'^[0-9a-f]{64}$')
        self.assertEqual(pins['05'],'e728b5e9cc74c91dfc2541dee1a404f98e3ff1b71b744512e4622d57a1dd5bdd')
