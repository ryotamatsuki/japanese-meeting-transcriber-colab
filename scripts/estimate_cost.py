"""Resource estimate from measured evidence, not an invoice. USD; 2026-10-29 rates."""
import argparse
from decimal import Decimal
import json
from pathlib import Path

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('evidence',type=Path)
    p.add_argument('--billable-seconds',type=Decimal,help='Prefer actual container duration from Modal dashboard')
    p.add_argument('--model-gib',type=Decimal,default=Decimal(0))
    p.add_argument('--retention-days',type=Decimal,default=Decimal(0));a=p.parse_args()
    evidence=json.loads(a.evidence.read_text())
    seconds=a.billable_seconds
    if seconds is None:
        seconds=Decimal(str(evidence['remote_function_seconds']))
    gpu=seconds*Decimal('0.000222')
    cpu=seconds*2*Decimal('0.0000131')
    memory=seconds*8*Decimal('0.00000222')
    storage=a.model_gib*a.retention_days/Decimal(30)*Decimal('0.09')
    print(json.dumps({'currency':'USD','seconds':str(seconds),'gpu':str(gpu),
          'cpu_2_physical_cores':str(cpu),'memory_8_GiB':str(memory),
          'volume_gross_before_free_allowance':str(storage),'total':str(gpu+cpu+memory+storage),
          'limits':'Compute estimate excludes build, startup/teardown/idle outside measured time and network charges. Storage ignores free allowance. No exchange-rate assumption.'},indent=2))
