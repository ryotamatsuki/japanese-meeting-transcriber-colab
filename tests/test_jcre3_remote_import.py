"""Reproduce Modal's remote module import without the client image factory."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


class JcreRemoteImportTests(unittest.TestCase):
    def test_cpu_worker_needs_no_local_image_factory_or_requirements_file(self):
        name='jcre3_remote_import_regression'
        path=Path(__file__).resolve().parents[1]/'modal_qwen_unseen_jcre3.py'
        spec=importlib.util.spec_from_file_location(name,path)
        module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{name:module,'modal_qwen_quality_ablation':None}), \
             patch('modal.is_local',return_value=False):
            spec.loader.exec_module(module)
            self.assertEqual(module.app.name,'kiroku-jcre3-unseen-pilot-20261031-01')
