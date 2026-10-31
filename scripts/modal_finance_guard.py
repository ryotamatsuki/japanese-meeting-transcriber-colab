"""Fail-closed operator evidence audit for Modal workspace budgets.

This validates *operator-provided* artifacts only. A successful validation is
not a live Modal setting read and cannot authorize a public release.
"""
from __future__ import annotations
import argparse, datetime as dt, json, math, re
from pathlib import Path
SHA=re.compile(r"^[0-9a-f]{64}$")

def _money(x, allow_zero=False):
    return type(x) in (int,float) and math.isfinite(x) and (x>=0 if allow_zero else x>0)

def audit(row, now=None):
    if not isinstance(row,dict) or row.get('schema_version') != 1:
        raise ValueError('Invalid evidence schema')
    now=now or dt.datetime.now(dt.timezone.utc)
    checks={}
    blockers=[]
    def check(name, condition, reason):
        checks[name]=bool(condition)
        if not checks[name]: blockers.append(reason)
    check('live_billing_api',
          row.get('live_billing_summary_access_confirmed') is True and
          row.get('billing_summary_run_id')==41079742581,
          'Read-only billing API run was not verified')
    check('workspace_usage_hard_cap',
          _money(row.get('workspace_budget_usd')) and
          row.get('workspace_budget_dashboard_confirmed') is True,
          'Pre-credit Workspace Budget must be confirmed in the private dashboard')
    check('workspace_net_spend_limit',
          _money(row.get('workspace_spend_limit_usd'),True) and
          row.get('workspace_spend_limit_dashboard_confirmed') is True,
          'Post-credit Workspace Spend Limit must be confirmed in the private dashboard')
    check('charge_notifications',
          row.get('charge_notifications_configured') is True and
          row.get('notification_destination_checked') is True,
          'Charge-alert delivery must be configured and its destination checked')
    try:
        stamp=dt.datetime.fromisoformat(row['verified_at_utc'].replace('Z','+00:00'))
        fresh=stamp.tzinfo is not None and dt.timedelta(0)<=now-stamp.astimezone(dt.timezone.utc)<=dt.timedelta(days=31)
    except (ValueError,KeyError,AttributeError,TypeError):
        fresh=False
    check('recent_owner_attestation',
          row.get('operator_role') in ('owner','manager') and fresh,
          'Fresh owner/manager attestation is required')
    hashes=row.get('private_evidence_hashes')
    keys=('workspace_budget_screenshot','spend_limit_screenshot','notification_setting_screenshot')
    check('private_evidence_recorded',
          isinstance(hashes,dict) and
          all(isinstance(hashes.get(k),str) and SHA.fullmatch(hashes[k]) for k in keys) and
          len(set(hashes[k] for k in keys))==3,
          'Record three distinct SHA-256 hashes of private dashboard screenshots (do not publish them)')
    return {'attestation_status':'COMPLETE' if all(checks.values()) else 'NOT_VERIFIED',
            'checks':checks,'blocking_conditions':blockers,
            'release_status':'NO_GO',
            'warning':'Screenshot hashes prove file consistency, NOT whether Modal settings are actually in effect. Operator must visually verify the live dashboard.'}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    report=audit(json.loads(a.evidence.read_text(encoding='utf-8')))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('MODAL_FINANCE_ATTESTATION',report['attestation_status'])
    if report['attestation_status']!='COMPLETE': raise SystemExit(2)
if __name__=='__main__': main()
