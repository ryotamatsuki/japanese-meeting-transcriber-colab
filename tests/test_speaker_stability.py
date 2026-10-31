"""Research candidate for diarization micro-switches; no model/ASR changes."""
import copy
import unittest

from transcriber.speaker_stability import short_switch_candidates, stabilize_short_switches
from transcriber.alignment import assign_and_group
from transcriber.processor import Config


def w(start, end, speaker, text):
    return {"start":start, "end":end, "speaker":speaker, "text":text}


class SpeakerStabilityTests(unittest.TestCase):
    def setUp(self):
        self.words=[
            w(0, .4, '話者1', '債務負担'),
            w(.4, .8, '話者1', '行為'),
            w(.85, 1.1, '話者2', 'があ'),
            w(1.14, 1.50, '話者1', 'って'),
            w(1.50, 1.95, '話者1', '契約した')
        ]

    def test_flags_suspicious_island_without_changing_baseline(self):
        baseline=copy.deepcopy(self.words)
        candidates=short_switch_candidates(self.words)
        self.assertEqual(len(candidates),1)
        self.assertEqual((candidates[0]['first_index'],candidates[0]['last_index']),(2,2))
        self.assertEqual(self.words,baseline)
        changed,audit=stabilize_short_switches(self.words)
        self.assertEqual(changed[2]['speaker'],'話者1')
        self.assertEqual(changed[2]['text'],'があ')
        self.assertEqual(changed[2]['start'],.85)
        self.assertEqual(audit['relabeled_words'],1)
        self.assertEqual(self.words,baseline)
        self.assertNotIn('text',str(audit))

    def test_real_short_backchannel_protected(self):
        words=copy.deepcopy(self.words)
        words[2]['text']='はい。'
        self.assertEqual(short_switch_candidates(words),[])
        self.assertEqual(short_switch_candidates(words,protect_backchannels=False)[0]['first_index'],2)

    def test_long_short_reply_and_nonadjacent_speech_not_relabelled(self):
        words=copy.deepcopy(self.words)
        words[2]['end']=1.5
        words[3]['start']=1.52
        self.assertEqual(short_switch_candidates(words),[])
        words=copy.deepcopy(self.words)
        words[3]['start']=1.6
        self.assertEqual(short_switch_candidates(words),[])
        words=copy.deepcopy(self.words)
        words[1]['speaker']='話者2'
        self.assertEqual(short_switch_candidates(words),[])

    def test_unknown_invalid_timestamps_and_alternating_speakers_protected(self):
        words=copy.deepcopy(self.words)
        words[2]['speaker']='話者不明'
        self.assertEqual(short_switch_candidates(words),[])
        words=copy.deepcopy(self.words)
        words[2]['end']=float('nan')
        self.assertEqual(short_switch_candidates(words),[])
        words=copy.deepcopy(self.words)
        words[3]['speaker']='話者3'
        self.assertEqual(short_switch_candidates(words),[])
        words=copy.deepcopy(self.words)
        words[2]['speaker']='話者1'
        self.assertEqual(short_switch_candidates(words),[])

    def test_threshold_guardrails(self):
        for value in (.0,.9,-.1):
            with self.assertRaises(ValueError):
                short_switch_candidates(self.words,max_island_seconds=value)
        for value in (-1,.5):
            with self.assertRaises(ValueError):
                short_switch_candidates(self.words,max_edge_gap=value)

    def test_exclusive_original_alignment_and_opt_in_only(self):
        asr=[{'start':x['start'],'end':x['end'],'words':[{'start':x['start'],'end':x['end'],'text':x['text']}]}
             for x in self.words]
        diar=[
            {'start':0.0,'end':.84,'speaker_id':'A'},
            {'start':.84,'end':1.12,'speaker_id':'B'},
            {'start':1.12,'end':2.0,'speaker_id':'A'}]
        before=copy.deepcopy((asr,diar))
        base,_,_=assign_and_group(asr,diar,True)
        experimental,_,_=assign_and_group(asr,diar,True,word_stability_ms=450)
        self.assertEqual([x['speaker'] for x in base],['話者1','話者2','話者1'])
        self.assertEqual([x['speaker'] for x in experimental],['話者1'])
        self.assertEqual(''.join(r['text'] for r in base),
                         ''.join(r['text'] for r in experimental))
        self.assertEqual((asr,diar),before)

    def test_cannot_enable_in_production_or_without_diarization(self):
        Config(word_stability_ms=0)
        with self.assertRaises(ValueError):
            Config(word_stability_ms=450)
        with self.assertRaises(ValueError):
            Config(word_stability_ms=450,quality_experiment=True,enable_diarization=False)
        with self.assertRaises(ValueError):
            Config(word_stability_ms=801,quality_experiment=True)
        self.assertEqual(Config(word_stability_ms=450,quality_experiment=True).word_stability_ms,450)


if __name__ == '__main__':
    unittest.main()
