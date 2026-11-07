"""
Design note item 72: the sensitivity of the interactive baseline EC^2 (ec2hyb.py, the posterior certificate with its
questions chosen by EC^2) to its two settings, the number K of posterior samples (80 in the paper) and the number of
questions per round (hbatch, 5 in the paper).  K and hbatch come from the environment (EC2_K, EC2_HBATCH).  The variant
ec2hyb_k{K}_h{H} is ec2hyb with these settings; with the defaults the variant keeps the name ec2hyb, so that a control
run can be compared with the rows of the paper field by field.  Every row also records K.

Nothing else changes: auto_noisy.py, auto_confirm.py, drd.py and ec2hyb.py stay as they are.  The command line is that
of auto_confirm.py, e.g. in confirm/ on a 4090 host:
  EC2_K=320 EC2_HBATCH=5 CONFIRM_TRUTH=full CONFIRM_ORACLE=gold CONFIRM_BATCH=3 python ec2sens.py run \
    --answers llm_fresh3_full_q35 --models q35 --variants ec2hyb_k320_h5 --datasets <the 23> --workers 6 --out <file>
"""
import os

import auto_confirm as ACF
import auto_noisy as AN
import ec2hyb            # patches auto_noisy.run_hybrid with the policy ec2 and registers the variant ec2hyb

K = int(os.environ.get("EC2_K", "80"))
H = int(os.environ.get("EC2_HBATCH", "5"))
NAME = "ec2hyb" if (K, H) == (80, 5) else f"ec2hyb_k{K}_h{H}"
ACF.VARIANTS[NAME] = dict(ACF.VARIANTS["ec2hyb"], hbatch=H)

_run_hybrid = AN.run_hybrid


def run_hybrid(*args, **kw):
    kw["K"] = K
    return _run_hybrid(*args, **kw)


AN.run_hybrid = run_hybrid
_job = ec2hyb.job


def job(args):
    out = _job(args)
    out["K"] = K
    return out


ACF.job = job      # auto_confirm.main submits this job; forked workers inherit the patches

if __name__ == "__main__":
    ACF.main()
