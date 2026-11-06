"""The scale experiment of design note item 53 on the candidate v6f.py: scale_run.py registers the synthetic relations at import, the
prior trains on the pool of CONFIRM_BATCH=2 as in item 53.  Usage (in confirm/, with CONFIRM_BATCH=2): python v6f_scale.py --answers A --variants V --budget 1000 --workers W --datasets D --out F"""
import sys
import scale_run                    # noqa: F401
import auto_common as AC
import v6f

sys.argv = ["v6f.py"] + sys.argv[1:]
AC.FRESH = []
v6f.main()
