"""Stage 10 research candidate gates keep production defaults frozen."""
import unittest
from transcriber.processor import Config


class JapaneseASRCandidateTests(unittest.TestCase):
    def test_production_default_unchanged(self):
        c=Config()
        self.assertEqual(c.asr_model,'large-v3')
        self.assertEqual(c.asr_beam_size,5)
        self.assertFalse(c.quality_experiment)

    def test_approval_required_for_turbo_and_beam8(self):
        with self.assertRaisesRegex(ValueError,'requires quality_experiment'):
            Config(asr_model='turbo')
        with self.assertRaisesRegex(ValueError,'requires quality_experiment'):
            Config(asr_beam_size=8)
        self.assertEqual(Config(quality_experiment=True,asr_model='turbo').asr_model,'turbo')
        self.assertEqual(Config(quality_experiment=True,asr_beam_size=8).asr_beam_size,8)

    def test_arbitrary_remote_repo_and_unknown_model_rejected(self):
        for path in ('../tmp/model','some-person/unsafe-model','large-v3-turbo'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                Config(quality_experiment=True,asr_model=path)


if __name__=='__main__':
    unittest.main()
