"""Human-time acceptance gate for nonconfidential Japanese meeting transcription.

Requires paired real-user timed tasks, minimum five distinct recordings.
Never infer time savings from synthetic model execution duration.
"""
import argparse
import json
import math
import statistics
from pathlib import Path


def assess(record):
    pairs=record.get('pairs')
    if not isinstance(pairs,list) or len(pairs)<5:
        raise ValueError('At least five independent real-user paired recordings required')
    if record.get('method')!='human_timed_crossover':
        raise ValueError('Must be real user timed crossover, not predicted duration')
    ids=set()
    results=[]
    order_counts={'manual_first':0,'assisted_first':0}
    for item in pairs:
        key=item.get('record_id')
        if not isinstance(key,str) or not (1<=len(key)<=80) or key in ids:
            raise ValueError('Invalid or duplicate recording identifier')
        ids.add(key)
        order=item.get('order')
        if order not in order_counts:
            raise ValueError('Crossover order missing')
        order_counts[order]+=1
        if item.get('manual_quality_pass') is not True or item.get('assisted_quality_pass') is not True:
            raise ValueError('Both final artifacts must pass independent quality verification')
        manual,assisted=item.get('manual_seconds'),item.get('assisted_seconds')
        if any(type(n) not in (int,float) or not math.isfinite(n) or n<=0 for n in (manual,assisted)):
            raise ValueError('Missing, invalid or estimated user timings')
        savings=1-float(assisted)/float(manual)
        results.append({'record_id':key,'manual_seconds':manual,
                        'assisted_seconds':assisted,'saving_percent':round(savings*100,3)})
    if min(order_counts.values())<2:
        raise ValueError('Unbalanced or unreported crossover assignment')
    median_savings=statistics.median(x['saving_percent'] for x in results)
    return {'records':len(results),
            'median_human_time_saving_percent':round(median_savings,3),
            'efficiency_gate':'PASS' if median_savings>=50 else 'NOT_MET',
            'release_status':'NO_GO',
            'quality_verified':True,'order_counts':order_counts,
            'per_record':results,
            'note':'Efficiency gate alone cannot authorize public beta release'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--observations',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    result=assess(json.loads(a.observations.read_text(encoding='utf-8')))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('HUMAN_TIME_NUMERIC_ONLY',json.dumps({k:v for k,v in result.items()
                                            if k!='per_record'},ensure_ascii=False))


if __name__=='__main__':main()
