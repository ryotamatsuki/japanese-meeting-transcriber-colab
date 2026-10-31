import copy
import unittest
from scripts.release_gate_v01 import audit


def synthetic_all_pass():
    return {
      'schema_version':1,
      'qwen_research_full10':{
          'run_id':41076994471,'completed':10,'failed':0,
          'reference_hashes_match':True,'research_extension_gate':'PASS'},
      'qwen_web':{
          'short_run_id':41079582347,'short_web_e2e_success':True,
          'short_explicit_deletion_verified':True,
          'longform':{'independent_recordings':2,'source_ids':['ingcrowd01','ingcrowd05'],'human_check_final_minute':True,
                      'edit_export_delete_verified':True,'fresh_runs_pass':True}},
      'quality':{
          'human_reference_cer_median_percent':14.9,
          'independent_natural_meetings':True,
          'human_reference_der_median_percent':29.9,
          'diarization_scored_on_final_mode':True,
          'human_annotated_three_speaker':3,'human_annotated_four_speaker':3,
          'licenses_confirmed':True,'references_are_human_verified':True},
      'security_and_retention':{
          'auth_csrf_pass':True,'physical_delete_verified':True,
          'stale_recovery_verified':True,'scheduled_cleanup_verified':True,
          'latest_ci_green':True},
      'billing':{
          'actual_billing_checked':True,'workspace_budget_hard_limit_configured':True,
          'charge_notifications_configured':True},
      'human_editing':{
          'paired_distinct_recordings':5,'median_saving_percent':55.,
          'independent_quality_pass':True,'human_timed_crossover':True},
      'restricted_nonconfidential_beta_only':True,
      'legal_review_for_audio_upload':True,
      'human_transcript_verification_required':True}


class ReleaseGateTests(unittest.TestCase):
    def test_all_valid_synthetic_data_exercises_go_branch_only(self):
        r=audit(synthetic_all_pass())
        self.assertEqual(r['release_status'],'GO')
        self.assertEqual(r['blocking_conditions'],[])

    def test_actual_missing_user_and_linguistic_metrics_must_block(self):
        e=synthetic_all_pass()
        e['quality']['human_reference_cer_median_percent']=31.437
        e['human_editing']={}
        e['qwen_web']['longform']={}
        r=audit(e)
        self.assertEqual(r['release_status'],'NO_GO')
        self.assertFalse(r['checks']['japanese_cer_target'])
        self.assertFalse(r['checks']['human_time_saving'])
        self.assertFalse(r['checks']['qwen_60min_web_e2e'])
        self.assertFalse(r['checks']['qwen_60min_human_tail_review'])

    def test_synthetic_two_source_60m_passes_web_but_not_human_listening(self):
        e=synthetic_all_pass()
        e['qwen_web']['longform']['human_check_final_minute']=False
        r=audit(e)
        self.assertTrue(r['checks']['qwen_60min_web_e2e'])
        self.assertFalse(r['checks']['qwen_60min_human_tail_review'])
        self.assertEqual(r['release_status'],'NO_GO')

    def test_two_repetitions_of_same_source_do_not_count_as_independent(self):
        e=synthetic_all_pass()
        e['qwen_web']['longform']['source_ids']=['ingcrowd01','ingcrowd01']
        r=audit(e)
        self.assertFalse(r['checks']['qwen_60min_web_e2e'])

    def test_3_speaker_only_cannot_pass_as_4_speaker(self):
        e=synthetic_all_pass()
        e['quality']['human_annotated_four_speaker']=0
        self.assertFalse(audit(e)['checks']['multispeaker_3_and_4'])

    def test_confirmed_billing_api_alone_does_not_prove_hard_budget(self):
        e=synthetic_all_pass()
        e['billing']['workspace_budget_hard_limit_configured']=False
        self.assertFalse(audit(e)['checks']['modal_budget_controls'])

    def test_bool_and_nan_are_not_valid_percentages(self):
        for bad in (True,float('nan'),-1,101):
            e=synthetic_all_pass()
            e['human_editing']['median_saving_percent']=bad
            self.assertFalse(audit(e)['checks']['human_time_saving'])

    def test_missing_scope_is_fail_closed(self):
        e=synthetic_all_pass()
        e['legal_review_for_audio_upload']=False
        self.assertFalse(audit(e)['checks']['scope_and_privacy'])


if __name__=='__main__':unittest.main()
