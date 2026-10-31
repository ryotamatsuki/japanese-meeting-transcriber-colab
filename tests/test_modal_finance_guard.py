import datetime as dt, unittest
from scripts.modal_finance_guard import audit
NOW=dt.datetime(2026,10,31,8,0,tzinfo=dt.timezone.utc)
def sample():
    return {'schema_version':1,'live_billing_summary_access_confirmed':True,
        'billing_summary_run_id':41079742581,'workspace_budget_usd':20,
        'workspace_budget_dashboard_confirmed':True,'workspace_spend_limit_usd':5,
        'workspace_spend_limit_dashboard_confirmed':True,
        'charge_notifications_configured':True,'notification_destination_checked':True,
        'operator_role':'owner','verified_at_utc':'2026-10-31T07:00:00Z',
        'private_evidence_hashes':{'workspace_budget_screenshot':'a'*64,
            'spend_limit_screenshot':'b'*64,'notification_setting_screenshot':'c'*64}}
class Tests(unittest.TestCase):
    def test_only_synthetic_control_logic(self):
        r=audit(sample(),NOW);self.assertEqual(r['attestation_status'],'COMPLETE')
        self.assertEqual(r['release_status'],'NO_GO')
    def test_missing_fails(self):
        self.assertEqual(audit({'schema_version':1},NOW)['attestation_status'],'NOT_VERIFIED')
    def test_bad_usage_limit(self):
        for v in (True,-2,0,None,float('nan'),'30'):
            s=sample();s['workspace_budget_usd']=v
            self.assertFalse(audit(s,NOW)['checks']['workspace_usage_hard_cap'])
    def test_zero_spend_limit_is_valid_when_confirmed(self):
        s=sample();s['workspace_spend_limit_usd']=0
        self.assertTrue(audit(s,NOW)['checks']['workspace_net_spend_limit'])
    def test_unverified_spend_limit_fails(self):
        s=sample();s['workspace_spend_limit_dashboard_confirmed']=False
        self.assertFalse(audit(s,NOW)['checks']['workspace_net_spend_limit'])
    def test_missing_alert_destination_fails(self):
        s=sample();s['notification_destination_checked']=False
        self.assertFalse(audit(s,NOW)['checks']['charge_notifications'])
    def test_duplicate_screenshot_fails(self):
        s=sample();s['private_evidence_hashes']['notification_setting_screenshot']='b'*64
        self.assertFalse(audit(s,NOW)['checks']['private_evidence_recorded'])
    def test_stale_naive_and_future_attestation_fails(self):
        for v in ('2026-09-01T00:00:00Z','2026-11-01T00:00:00Z','2026-10-31T07:00:00'):
            s=sample();s['verified_at_utc']=v
            self.assertFalse(audit(s,NOW)['checks']['recent_owner_attestation'])
    def test_non_owner_fails(self):
        s=sample();s['operator_role']='viewer'
        self.assertFalse(audit(s,NOW)['checks']['recent_owner_attestation'])
    def test_read_only_access_is_not_budget_evidence(self):
        s=sample();s['workspace_budget_dashboard_confirmed']=False
        self.assertFalse(audit(s,NOW)['checks']['workspace_usage_hard_cap'])
if __name__=='__main__': unittest.main()
