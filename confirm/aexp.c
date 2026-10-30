/*
 * Attribute exploration (Ganter's NextClosure with an expert) for design note item 44, the baseline of Sec. 6.
 * The objects of the context are the agree sets of r, so the context closure of P is cl_r(P), the attributes that
 * the minimal FDs of r give in one step, intersected with every counterexample that contains P.  Background
 * knowledge Sigma0.  The expert answers from Sigma*: P -> P'' holds iff P'' is inside cl_Sigma*(P), and the
 * counterexample is cl_Sigma*(P), or with the argument "max" (exploratory, added after the first results) a largest
 * one: a maximal set of Sigma* for the first attribute A of P'' outside cl_Sigma*(P), grown from cl_Sigma*(P) by
 * asking C + B -> A in attribute order.  Counts the implication questions (yes, no) and the unit questions that our
 * designer would answer to give the same answers (aexp.py); a unit question that the context refutes (an object
 * contains C + B but not A) or that L implies is not counted.
 * Input on stdin (masks as decimal integers, attribute i is bit i):
 *   n seconds
 *   k0, then k0 lines "lhs rhs"      Sigma0
 *   kd, then kd lines "lhs rhs"      the minimal FDs of r (rhs one bit)
 *   ks, then ks lines "lhs rhs"      Sigma* (the designer's FDs, Sigma0 included)
 * Output on stdout: one JSON object.
 * Build: gcc -O2 -o aexp aexp.c
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <time.h>

typedef uint64_t M;
typedef struct { M l, r; } Imp;
typedef struct { Imp *a; int k, cap; } Imps;

static void push(Imps *f, M l, M r) {
    if (f->k == f->cap) { f->cap = f->cap ? 2 * f->cap : 64; f->a = realloc(f->a, f->cap * sizeof(Imp)); }
    f->a[f->k].l = l; f->a[f->k].r = r; f->k++;
}

static void readimps(Imps *f) {
    int k; unsigned long long l, r;
    if (scanf("%d", &k) != 1) exit(2);
    for (int i = 0; i < k; i++) { if (scanf("%llu %llu", &l, &r) != 2) exit(2); push(f, (M)l, (M)r); }
}

/* the closure of x under a set of implications */
static M closure(M x, const Imps *f) {
    int ch = 1;
    while (ch) {
        ch = 0;
        for (int i = 0; i < f->k; i++)
            if ((f->a[i].l & ~x) == 0 && (f->a[i].r & ~x)) { x |= f->a[i].r; ch = 1; }
    }
    return x;
}

static Imps L, D, S, CE;   /* L: Sigma0 and the accepted implications; D: the FDs of r; CE: the counterexamples (l) */
static int n;

/* P'': the attributes that every object containing p has */
static M ctx(M p) {
    M x = p;
    for (int i = 0; i < D.k; i++)
        if ((D.a[i].l & ~p) == 0) x |= D.a[i].r;      /* minimal FDs of r: one step gives cl_r(p) */
    for (int i = 0; i < CE.k; i++)
        if ((p & ~CE.a[i].l) == 0) x &= CE.a[i].l;
    return x;
}

/* the lectically next L-closed set after a, or a itself if there is none */
static M next_closure(M a, int *last) {
    for (int i = n - 1; i >= 0; i--) {
        M b = (M)1 << i;
        if (a & b) { a &= ~b; continue; }
        M c = closure(a | b, &L);
        if (((c & ~a) & (b - 1)) == 0) return c;
    }
    *last = 1;
    return a;
}

int main(int argc, char **argv) {
    int maxce = argc > 1 && argv[1][0] == 'm';
    double limit;
    if (scanf("%d %lf", &n, &limit) != 2 || n > 63) return 2;
    readimps(&L); readimps(&D); readimps(&S);
    int k0 = L.k;
    long long visited = 0, yes = 0, no = 0, unit = 0, unit_yes = 0;
    int finished = 1, last = 0;
    clock_t t0 = clock();
    M a = closure(0, &L);
    while (!last) {
        visited++;
        M known_yes = a, known_no = 0;          /* the unit answers given on a so far */
        for (;;) {
            M pp = ctx(a);
            if (pp == a) break;                 /* a is an intent: no question */
            M s = closure(a, &S);               /* cl_Sigma*(a): the expert's answer or counterexample */
            for (int i = 0; i < n; i++) {       /* the unit questions a -> A that settle the answer */
                M b = (M)1 << i;
                if (!(pp & b) || (known_yes & b) || (known_no & b)) continue;
                unit++;
                if (s & b) { unit_yes++; known_yes = closure(known_yes | b, &L); }
                else known_no |= b;
            }
            if ((pp & ~s) == 0) { yes++; push(&L, a, pp); break; }
            no++;
            if (maxce) {                        /* grow s into a maximal set of Sigma* for a */
                int ia = __builtin_ctzll(pp & ~s);
                M ab = (M)1 << ia;
                for (int i = 0; i < n; i++) {
                    M b = (M)1 << i;
                    if ((s & b) || i == ia) continue;
                    M q = s | b;
                    if (closure(q, &L) & ab) continue;              /* L implies q -> A */
                    if (!(ctx(q) & ab)) { s = closure(q, &L); continue; }   /* an object refutes q -> A */
                    unit++;
                    if (closure(q, &S) & ab) unit_yes++;
                    else s = closure(q, &L);
                }
            }
            push(&CE, s, 0);
        }
        if ((visited & 0xffff) == 0 && (double)(clock() - t0) / CLOCKS_PER_SEC > limit) { finished = 0; break; }
        a = next_closure(a, &last);
    }
    double secs = (double)(clock() - t0) / CLOCKS_PER_SEC;
    /* L is equivalent to Sigma* iff each implies the other */
    int equivalent = finished;
    for (int i = 0; equivalent && i < S.k; i++) if (S.a[i].r & ~closure(S.a[i].l, &L)) equivalent = 0;
    for (int i = 0; equivalent && i < L.k; i++) if (L.a[i].r & ~closure(L.a[i].l, &S)) equivalent = 0;
    printf("{\"finished\": %d, \"visited\": %lld, \"yes\": %lld, \"no\": %lld, \"unit\": %lld, \"unit_yes\": %lld, "
           "\"basis\": %d, \"counterexamples\": %d, \"equivalent\": %d, \"secs\": %.1f}\n",
           finished, visited, yes, no, unit, unit_yes, L.k - k0, CE.k, equivalent, secs);
    return 0;
}
