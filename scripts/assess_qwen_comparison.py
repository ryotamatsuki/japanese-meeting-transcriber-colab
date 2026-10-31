"""Assess a paired research run without confusing screening with commercial readiness."""
import argparse
import json
import math
from pathlib import Path


def assess(result):
    conditions=result['conditions']
    if len(conditions)!=2 or conditions[0].get('name')!='baseline_30':
        raise ValueError('Expected one baseline and one preregistered candidate')
    if result.get('experiment_mode') not in ('boundary','longchunk','pcm'):
        raise ValueError('Unknown paired experiment')
    if not all(isinstance(result.get(k),str) and len(result[k])==64 and
               all(c in '0123456789abcdef' for c in result[k])
               for k in ('audio_sha256','reference_eaf_sha256')):
        raise ValueError('Missing paired input identity')
    if result.get('model')!='Qwen/Qwen3-ASR-1.7B':
        raise ValueError('Model changed')
    if result['experiment_mode']=='pcm' and not result.get('alternative_audio_sha256'):
        raise ValueError('Missing lossless input identity')
    report={'record_id':result['record_id'],'experiment_mode':result['experiment_mode'],
            'criterion':'absolute cpCER improvement >=3pp; CER no worse; both succeed',
            'screening_pass':False,'commercial_ready':False,
            'commercial_blockers':['single development recording',
                'no independent meeting validation','no measured human correction study'],
            'conditions_succeeded':all(v.get('status')=='success' for v in conditions)}
    if not report['conditions_succeeded']:
        report['decision']='candidate not adopted: processing failure'
        report['failures']=[{'name':v['name'],'stage':v.get('failure_stage','unknown'),
                             'error_class':v.get('error_class','unknown')}
                            for v in conditions if v.get('status')!='success']
        return report
    for condition in conditions:
        for key in ('cpcer','flattened_cer','inference_and_eval_seconds'):
            value=condition[key]
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
                raise ValueError('Invalid numeric metric')
    baseline,candidate=conditions
    gain=(baseline['cpcer']-candidate['cpcer'])*100
    cer_change=(candidate['flattened_cer']-baseline['flattened_cer'])*100
    report.update({'cpcer_improvement_pp':gain,'cer_change_pp':cer_change,
                   'screening_pass':gain>=3.0 and cer_change<=0.0,
                   'candidate_to_baseline_time_ratio':(
                       candidate['inference_and_eval_seconds']/baseline['inference_and_eval_seconds']
                       if baseline['inference_and_eval_seconds']>0 else None)})
    report['decision']=('eligible for independent evaluation; no production adoption'
                        if report['screening_pass'] else 'candidate not adopted: screening criterion unmet')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('metrics',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=assess(json.loads(args.metrics.read_text()))
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    main()
