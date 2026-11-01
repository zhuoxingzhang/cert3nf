"""
The interactive baseline of design note item 52: the posterior certificate (auto_noisy.run_hybrid, variants rbhyb and
rbhyb0) with its questions chosen by EC^2 (Golovin, Krause and Ray, NIPS 2010) instead of by the largest posterior
marginal.  The hypotheses are the posterior samples, with equal weights; their classes are the decision regions of the
greedy cover drd.classes_cover; a question scores the expected weight of the edges it cuts, an edge joining two samples
of different classes (drd.ec2_score).  A round asks the five informative candidates of largest score; ties, among them
the candidates of score 0 that the sound check asks the designer to confirm, keep the marginal order of rbhyb.

Nothing else changes: the run_hybrid used here is auto_noisy's own source with one added branch in its choice of
questions (the replaced lines must occur exactly once), and auto_noisy.py, auto_confirm.py and drd.py stay as they are.
Variants ec2hyb and ec2hyb0 are rbhyb and rbhyb0 with policy "ec2"; the command line is that of auto_confirm.py, e.g. in
confirm/:
  CONFIRM_TRUTH=full CONFIRM_ORACLE=gold CONFIRM_BATCH=2 python ec2hyb.py run --answers llm_fresh2_full_q35 \
    --models q35 --variants ec2hyb,ec2hyb0 --datasets <the twelve> --workers 7 --out ec2_results/results_ec2_full.jsonl
"""
import inspect

import auto_confirm as ACF
import auto_noisy as AN
import drd

OLD = """        else:
            key = lambda q: (-cnt[q], -inst.pi[q])
"""
NEW = """        elif policy == "ec2":
            sc = ec2_scores(ds, G, samples, informative)
            key = lambda q: (-sc[q], -cnt[q], -inst.pi[q])
        else:
            key = lambda q: (-cnt[q], -inst.pi[q])
"""


def ec2_scores(ds, G, samples, cands):
    """drd.ec2_score of every candidate in cands, with the classes of drd.classes_cover; G[d][i] is
    inst.good(d, samples[i], eps) (drd.good_matrix), so the regions are read off G instead of being tested again"""
    left, label = set(range(len(samples))), {}
    regions = {d: {i for i in left if G[d][i]} for d in ds}
    while left:
        d = max(regions, key=lambda d: len(regions[d] & left))
        got = regions[d] & left
        if not got:
            for i in left:
                label[i] = ("own", samples[i])
            break
        for i in got:
            label[i] = d
        left -= got
    labels = [label[i] for i in range(len(samples))]
    return {q: drd.ec2_score(labels, samples, q) for q in cands}


src = inspect.getsource(AN.run_hybrid)
assert src.count(OLD) == 1, "auto_noisy.run_hybrid changed: the choice of questions is not where ec2hyb expects it"
ns = dict(vars(AN), ec2_scores=ec2_scores)
exec(compile(src.replace(OLD, NEW), AN.__file__, "exec"), ns)
AN.run_hybrid = ns["run_hybrid"]
ACF.VARIANTS["ec2hyb"] = dict(ACF.VARIANTS["rbhyb"], policy="ec2")
ACF.VARIANTS["ec2hyb0"] = dict(ACF.VARIANTS["rbhyb0"], policy="ec2")


_job = ACF.job


def job(args):
    return _job(args)


ACF.job = job      # the workers of auto_confirm.main run this module's job, so a spawned worker imports the patch too

if __name__ == "__main__":
    ACF.main()
