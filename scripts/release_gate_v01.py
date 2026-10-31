"""Fail-closed v0.1 release gate. Research success != human-ready product GO.

Only accepts independently verified, licensed human-reference evidence.
Never use synthetic test fixtures or the same recordings in place of new
multi-speaker and hands-on human studies. CI tests verify logic, not readiness.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def _ok_number(v, *, min_value=0., max_value=None):
    return (type(v) in (int,float) and math.isfinite(v)
            and v>=min_value and (max_value is None or v<=max_value))


def audit(evidence):
    if not isinstance(evidence,dict) or evidence.get('schema_version')!=1:
        raise ValueError('Unsupported evidence manifest')
    blockers=[]
    checks={}

    def check(name,predicate,reason):
        checks[name]=bool(predicate)
        if not checks[name]:
            blockers.append(reason)

    stage17=evidence.get('qwen_research_full10') or {}
    check('qwen_all10_reference_integrity',
          stage17.get('run_id')==41076994471
          and stage17.get('completed')==10
          and stage17.get('failed')==0
          and stage17.get('reference_hashes_match') is True
          and stage17.get('research_extension_gate')=='PASS',
          'Stage17 10-record Qwen research evidence incomplete')

    qwen_web=evidence.get('qwen_web') or {}
    check('qwen_11min_live_web',
          qwen_web.get('short_run_id')==41079582347
          and qwen_web.get('short_web_e2e_success') is True
          and qwen_web.get('short_explicit_deletion_verified') is True,
          'Qwen short authenticated Web E2E not verified')

    longform=qwen_web.get('longform') or {}
    source_ids=longform.get('source_ids')
    check('qwen_60min_web_e2e',
          type(longform.get('independent_recordings')) is int
          and longform['independent_recordings']>=2
          and isinstance(source_ids,list)
          and len(source_ids)>=2 and all(isinstance(s,str) and s for s in source_ids)
          and len(set(source_ids))>=2
          and longform.get('edit_export_delete_verified') is True
          and longform.get('fresh_runs_pass') is True,
          'Qwen 60-minute Web E2E not reproduced with two distinct authorized audio sources')
    # A synthetic repeat stress test may pass the E2E gate without human
    # listening; preserve the listening requirement as a separate mandatory gate.
    check('qwen_60min_human_tail_review',
          longform.get('human_check_final_minute') is True,
          'No verified human listening of the final minute on 60-minute recordings')

    quality=evidence.get('quality') or {}
    check('japanese_cer_target',
          _ok_number(quality.get('human_reference_cer_median_percent'),max_value=15)
          and quality.get('independent_natural_meetings') is True,
          'CER median <=15% on independent naturally recorded Japanese meetings not shown')
    check('speaker_der_target',
          _ok_number(quality.get('human_reference_der_median_percent'),max_value=30)
          and quality.get('diarization_scored_on_final_mode') is True,
          'DER median <=30% on actual chosen speaker mode not shown')
    check('multispeaker_3_and_4',
          type(quality.get('human_annotated_three_speaker')) is int
          and type(quality.get('human_annotated_four_speaker')) is int
          and quality['human_annotated_three_speaker']>=3
          and quality['human_annotated_four_speaker']>=3
          and quality.get('licenses_confirmed') is True
          and quality.get('references_are_human_verified') is True,
          'Need licensed independent human-verified 3-speaker AND 4-speaker meetings')

    security=evidence.get('security_and_retention') or {}
    check('security_and_retention',
          security.get('auth_csrf_pass') is True
          and security.get('physical_delete_verified') is True
          and security.get('stale_recovery_verified') is True
          and security.get('scheduled_cleanup_verified') is True
          and security.get('latest_ci_green') is True,
          'Auth, cleanup schedule, stale job recovery, or latest CI evidence missing')

    billing=evidence.get('billing') or {}
    check('modal_budget_controls',
          billing.get('actual_billing_checked') is True
          and billing.get('workspace_budget_hard_limit_configured') is True
          and billing.get('charge_notifications_configured') is True,
          'Actual Modal usage, workspace budget and charge alerts not operator-verified')

    human=evidence.get('human_editing') or {}
    check('human_time_saving',
          type(human.get('paired_distinct_recordings')) is int
          and human['paired_distinct_recordings']>=5
          and _ok_number(human.get('median_saving_percent'),min_value=50,max_value=100)
          and human.get('independent_quality_pass') is True
          and human.get('human_timed_crossover') is True,
          'Five human-timed crossover tasks with >=50% median saving not measured')

    check('scope_and_privacy',
          evidence.get('restricted_nonconfidential_beta_only') is True
          and evidence.get('legal_review_for_audio_upload') is True
          and evidence.get('human_transcript_verification_required') is True,
          'Privacy/scope and final human verification requirements not confirmed')

    return {'release_status':'GO' if all(checks.values()) else 'NO_GO',
            'checks':checks,'blocking_conditions':blockers,
            'go_checks_passed':sum(checks.values()),'total_checks':len(checks),
            'warning':('Metrics and attestations must be grounded in actual runs/authorization, '
                       'not the synthetic fixtures used by unit tests.')}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    report=audit(json.loads(a.evidence.read_text(encoding='utf-8')))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('RELEASE_GATE',json.dumps(report,ensure_ascii=False))
    if report['release_status']!='GO':
        raise SystemExit(2)


if __name__=='__main__':main()
