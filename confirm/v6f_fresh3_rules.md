# Confirmatory evaluation of the frozen method on the third batch: rules

Written on 2026-11-05, before any method ran on a relation of this batch.

## Frozen code

| File | md5 (first 12 hex digits) | Role |
|---|---|---|
| `v6f.py` | e2a6af907596 | the method; main form `v6s\|lc+hone+kf+rl`, statistics only |
| `v5.py` | 8e0e04aeb2ce | comparator v5, v5s, v5n |
| `v5tol.py` | f3ec39c04c59 | comparator for a designer who errs |
| `v5tau.py` | 45d73a6e86b3 | comparator for the tolerance |
| `e3/truth/fresh3.json` | d1c6f67e18fc | documented FDs of the 23 relations, audited blind |

## Relations

Class A, 7 relations with a generated schema: `tpcc_order_line`, `tpcc_stock`, `tpcc_customer`, `twitter_tweets`, `synthea_encounters`, `synthea_claims`, `synthea_claims_transactions`.

Class B, 16 relations with real data: `hgnc`, `gleif`, `onspd`, `fec_candidate`, `fec_committee`, `fec_linkage`, `ourairports_airports`, `ourairports_navaids`, `ourairports_frequencies`, `nppes_npidata`, `companieshouse`, `openpayments_general`, `openpayments_profile`, `stackexchange_posts`, `stackexchange_users`, `stackexchange_postlinks`.

None of them trains anything. The prior and the answer models are fitted on the 36 earlier relations.

## How the rules are judged

Every rule is judged per truth (`full`, `sure`) on the 23 relations, and reported for class A and class B apart.
A claim that holds on one class only is claimed on that class only.
The budget is 1000 answers, and an uncertified run counts as 1000.
Paired ratios are per relation.
The price is the exact smallest cover plus the held sets, computed from the truth and the data alone before any method ran (`v6f_fresh3/price_gold.json`).

## Rules

- **V1, fewer answers.** The paired ratio of the main form over frozen v5 with the LLM has median ≤ 0.9, and the total number of answers is lower.
- **V2, exact.** Every certified run passes `check_cert.py` with no disagreement and every premise right for gold. A certified design may be not good for gold only on the relations pre-listed below.
- **V3, beats EC² on the same question pool.** The paired ratios of the main form over `ec2full` and over `ec2full0`, each the median of three seeds, both have median ≤ 1. A relation whose three seeds do not finish within 72 hours of wall clock leaves V3 and is reported.
- **V4, close to the price.** Answers over price has median ≤ 1.6 and upper quartile ≤ 2. Every certified run has at least m* no answers; a violation is a code error.
- **V5, bounded damage.** The main form certifies at least as many relations as `v5n`. Its answers are at most those of `v5n` + b + the sets answered yes + the missed first guesses on at least 90% of the relations. At the end of budget 100, designs good for gold number at least those of `rbhyb` (median of three seeds, summed over relations), with the wrong posterior certificates of `rbhyb` reported beside them.

## Pre-listed exception

These documented FDs are violated by the data, listed from `witness_fresh3.log` on 2026-11-04 before any method ran.
Under `sure` there are none.
Under `full` there are 28: `tpcc_order_line` 1, `hgnc` 22, `onspd` 3, `ourairports_airports` 1, `ourairports_frequencies` 1.

## Reported without a rule

The LLM form and the second model, budget 100 certificates and good designs, ablations, careful mode and a designer who errs, the tolerance, `v5s`, relations won and lost against v5, the fully automated methods, and the scale experiment (not on this batch).

## Consequences

If V1 or V2 fails, the paper stays with v5.
If another rule fails, the matching claim is narrowed.

## Stopping rule

The evaluation runs once.
After seeing results, the method, the rules and the relations do not change.
If a code error is found, it is fixed, everything is rerun, and both results are reported.
