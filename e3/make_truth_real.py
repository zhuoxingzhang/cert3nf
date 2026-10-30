"""
Writes truth/documented.json and truth/screened.json, the gold Sigma* of the real data sets of E3.

documented: the FD sets of documented rules of prior work (tools/data/fds/meaningful/<set>.json, written by
src/meaningful.py, whose comments and README cite the sources).  The base set of a data set is "sure"; the FDs that
a variant adds (food+c1, uk+admin, hospital-all), whose status prior work marks as doubtful, are "sure": false.
screened: the meaningful FDs that a screening note (2026-10-12) kept after screening the discovered FDs by
the meaning of their attributes; an FD the screening kept only as borderline is "sure": false.

Usage:  python make_truth_real.py <prior work/tools directory>
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOLO = "HoloClean (Rekatsinas et al., PVLDB 10(11), 2017)"
PAF = "Royal Mail PAF Programmers' Guide, Edition 7 (pp. 14 and 17)"
DS4 = "TPC-DS v4.0.0"


def load(tools, s):
    with open(os.path.join(tools, "data", "fds", "meaningful", s + ".json"), encoding="utf-8") as fh:
        d = json.load(fh)
    nm = d["names"]
    return nm, [([nm[i] for i in f["lhs"]], [nm[i] for i in f["rhs"]]) for f in d["fds"]]


# justification and clause of each FD of the documented sets, keyed by its left-hand side
WHY = {
    "food": {
        ("InspectionID",): ("City of Chicago, Food Inspections (4ijn-s7e5)", "InspectionID identifies the inspection record."),
        ("Zip",): (HOLO + ", Fig. 1, c2", "A zip code lies in one city and state."),
        ("City", "State", "Address"): (HOLO + ", Fig. 1, c3", "An address in a city and state has one zip code."),
        ("License",): (HOLO + ", Sec. 6.1", "Conflicting zip codes and facility types of one licensed establishment are errors."),
        ("License", "InspectionDate"): (HOLO + ", Sec. 6.1", "An establishment has one result per inspection date."),
        ("DBAName",): (HOLO + ", Fig. 1, c1; prior work variant food+c1", "Listed by HoloClean, but it fails for chains, whose outlets share the name and have many zip codes."),
    },
    "uk": {
        ("TransactionID",): ("HM Land Registry, Price Paid Data 2024", "TransactionID identifies the transaction."),
        ("PAON", "SAON", "Street", "Locality", "Town"): (PAF, "A delivery point (house number or name, flat, thoroughfare, locality, post town) has one postcode."),
        ("Postcode",): (PAF, "A postcode has one thoroughfare, dependent locality and post town."),
        ("Postcode", "admin"): ("prior work variant uk+admin", "Administrative areas follow the postcode only approximately."),
        ("District",): ("prior work variant uk+admin", "A district lies in one county only approximately (unitary authorities)."),
    },
    "hospital": {
        ("ZipCode",): (HOLO + ", denial constraints of the hospital data", "A zip code lies in one city and state."),
        ("PhoneNumber",): (HOLO + ", denial constraints of the hospital data", "A phone number belongs to one hospital location."),
        ("ProviderNumber", "MeasureCode"): (HOLO + ", denial constraints; prior work (key of the measurement)", "A hospital has one score, sample and state average per measure."),
        ("MeasureCode",): (HOLO + ", denial constraints of the hospital data", "A measure code has one name and condition."),
        ("State", "MeasureCode"): (HOLO + ", denial constraints of the hospital data", "The state average of a measure is one value per state."),
        ("ProviderNumber",): ("prior work (key of the hospital)", "The provider number identifies the hospital."),
        ("Address1", "City", "State"): ("prior work (address rule c3 of food)", "An address in a city and state has one zip code."),
        "all": ("prior work variant hospital-all: the other published constraint lists of the hospital data (HoloClean repository, QCRI gold, Raha, Martin et al. PVLDB 2025) that hold on its clean version", "Published as a constraint of the hospital data; doubtful as a rule of the domain."),
    },
    "tpcds-core": {
        ("i_item_sk",): (DS4 + ", primary key of ITEM", "The surrogate key identifies the item revision."),
        ("s_store_sk",): (DS4 + ", primary key of STORE", "The surrogate key identifies the store revision."),
        ("d_date_sk",): (DS4 + ", primary key of DATE_DIM", "The surrogate key identifies the day."),
        ("d_date",): (DS4 + ", DATE_DIM", "DATE_DIM has one row per date."),
        ("i_item_sk", "ss_ticket_number"): (DS4 + ", primary key of STORE_SALES", "A ticket has one line per item."),
        ("ss_ticket_number",): ("dsdgen (w_store_sales.c, mk_master), not the specification", "The generator draws the date and the store once per ticket."),
        ("i_item_id", "d_date"): (DS4 + ", Clause 1.3.3 (historical dimensions)", "One revision of an item is active at a date, and a sale refers to the revision active on its date."),
        ("s_store_id", "d_date"): (DS4 + ", Clause 1.3.3 (historical dimensions)", "One revision of a store is active at a date."),
    },
}


def documented(tools):
    out = {}
    for ds, base, variant in (("hospital", "hospital", "hospital-all"), ("food", "food", "food+c1"),
                              ("pricepaid", "uk", "uk+admin"), ("tpcds_core", "tpcds-core", None)):
        names, fds = load(tools, base)
        extra = []
        if variant:
            vn, vf = load(tools, variant)
            assert vn == names
            extra = [f for f in vf if f not in fds]
        why = WHY[base]
        truth = []
        for lhs, rhs in fds + extra:
            doubtful = (lhs, rhs) in extra or (base == "tpcds-core" and lhs == ["ss_ticket_number"])
            key = tuple(lhs)
            if base == "uk" and (lhs, rhs) in extra and lhs == ["Postcode"]:
                key = ("Postcode", "admin")
            if base == "hospital" and (lhs, rhs) in extra:
                key = "all"
            clause, just = why[key]
            truth.append({"lhs": lhs, "rhs": rhs, "sure": not doubtful, "clause": clause, "justification": just})
        spec = {"attributes": names, "truth": truth,
                "construction": f"prior work FD set '{base}'" + (f" with the additions of '{variant}' as unsure" if variant else ""),
                "random_columns": None, "gold_design": None,
                "gold_design_note": "No normalized design is published for this data; truth_design gives the 3NF designs of Sigma*."}
        if ds == "tpcds_core":
            spec["gold_design"] = [
                {"name": "store_sales", "attributes": ["ss_ticket_number", "i_item_sk", "ss_quantity", "ss_sales_price", "d_date_sk", "s_store_sk"], "keys": [["i_item_sk", "ss_ticket_number"]]},
                {"name": "item", "attributes": ["i_item_sk", "i_item_id", "i_item_desc", "i_current_price"], "keys": [["i_item_sk"]]},
                {"name": "store", "attributes": ["s_store_sk", "s_store_id", "s_store_name"], "keys": [["s_store_sk"]]},
                {"name": "date_dim", "attributes": ["d_date_sk", "d_date"], "keys": [["d_date_sk"], ["d_date"]]}]
            spec["gold_design_note"] = "The TPC-DS tables, projected to the 12 attributes; ss_item_sk, ss_sold_date_sk and ss_store_sk are merged into i_item_sk, d_date_sk and s_store_sk."
        out[ds] = spec
    return {"source": "prior work, tools/src/meaningful.py and README (Meaningful FD sets), with the data of tools/src/documented.py",
            "truth_kind": "documented rules",
            "rule": "Sigma* is the FD set of documented rules that prior work lists for the data set (sure); the FDs added by its variant, whose status prior work marks as doubtful, are unsure. The data are cleaned by the greedy subset repair of documented.py until the base set holds, so the sure FDs hold on the instance by construction.",
            "datasets": out}


SCREEN = "a screening note (2026-10-12)"
NAMES = {   # prior work tools/src/fd_names.py
    "abalone": ["sex", "length", "diameter", "height", "whole_weight", "shucked_weight", "viscera_weight", "shell_weight", "rings"],
    "adult": ["age", "workclass", "fnlwgt", "education", "education_num", "marital_status", "occupation", "relationship", "race", "sex", "capital_gain", "capital_loss", "hours_per_week", "native_country", "income"],
    "breast": ["sample_code", "clump_thickness", "cell_size_uniformity", "cell_shape_uniformity", "marginal_adhesion", "epithelial_cell_size", "bare_nuclei", "bland_chromatin", "normal_nucleoli", "mitoses", "class"],
    "bridges": ["identif", "river", "location", "erected", "purpose", "length", "lanes", "clear_g", "t_or_d", "material", "span", "rel_l", "type"],
    "echo": ["survival", "still_alive", "age_at_heart_attack", "pericardial_effusion", "fractional_shortening", "epss", "lvdd", "wall_motion_score", "wall_motion_index", "mult", "name", "group", "alive_at_1"],
    "hepatitis": ["class", "age", "sex", "steroid", "antivirals", "fatigue", "malaise", "anorexia", "liver_big", "liver_firm", "spleen_palpable", "spiders", "ascites", "varices", "bilirubin", "alk_phosphate", "sgot", "albumin", "protime", "histology"],
    "letter": ["lettr", "x_box", "y_box", "width", "high", "onpix", "x_bar", "y_bar", "x2bar", "y2bar", "xybar", "x2ybr", "xy2br", "x_ege", "xegvy", "y_ege", "yegvx"],
    "ncvoter": ["voter_id", "voter_reg_num", "name_prefix", "first_name", "middle_name", "last_name", "name_suffix", "age", "gender", "race", "ethnic", "street_address", "city", "state", "zip_code", "full_phone_num", "birth_place", "register_date", "download_month"],
}


def screened():
    def rest(ds, a):
        return [x for x in NAMES[ds] if x != a]
    T = {
        "abalone": ([], "No domain rule: every minimal FD has three to six continuous measurements on its left-hand side, an accident of 4,177 records. There is no key."),
        "adult": ([(["education"], ["education_num"], True, "education_num is the numeric code of education (a lookup pair)."),
                   (["education_num"], ["education"], True, "As above.")],
                  "Apart from the lookup pair, every minimal FD contains fnlwgt (a near-unique sampling weight) and is accidental."),
        "breast": ([], "sample_code is the patient number, but a patient was sampled several times, so it is no key; sample_code with a cell feature determining class is an accident of the sample."),
        "bridges": ([(["identif"], rest("bridges", "identif"), True, "identif is the identifier of the bridge (the key)."),
                     (["location"], ["river"], True, "A location code lies on one river."),
                     (["location", "erected"], ["identif"], False, "One bridge per location and year of erection; kept by the screening only as borderline.")],
                    "The FDs on erected and length are accidents of 108 records."),
        "echo": ([(["wall_motion_index", "mult"], ["wall_motion_score"], True, "The UCI documentation defines wall_motion_index as wall_motion_score divided by the number of segments seen, and mult as a derived quantity, so the two determine the score.")],
                 "The constant column name is dropped. The other minimal FDs are accidents of 132 records; alive_at_1 is derived from survival and still_alive in the documentation, but the data do not satisfy that FD."),
        "hepatitis": ([], "Symptom combinations of 155 patient records; no domain rule."),
        "letter": ([], "Every minimal FD has 11 to 13 image statistics determining the letter; no domain rule."),
        "ncvoter": ([(["voter_id"], rest("ncvoter", "voter_id"), True, "voter_id identifies the voter."),
                     (["voter_reg_num"], rest("ncvoter", "voter_reg_num"), True, "The registration number identifies the voter record."),
                     (["street_address"], ["city"], True, "An address lies in one city."),
                     (["street_address"], ["zip_code"], True, "An address has one zip code.")],
                    "The constant column state is dropped. The FDs from names to age, race and so on are accidents of the 1,000-record sample; zip_code -> city fails on it."),
    }
    out = {}
    for ds, (fds, note) in T.items():
        out[ds] = {"attributes": NAMES[ds],
                   "truth": [{"lhs": l, "rhs": r, "sure": s, "clause": SCREEN, "justification": j} for l, r, s, j in fds],
                   "construction": "HPI repeatability data set (" + ds + "), duplicates removed",
                   "random_columns": note, "gold_design": None,
                   "gold_design_note": "No design is published; truth_design gives the 3NF designs of Sigma*."}
    return {"source": SCREEN + ": the discovered FDs of prior work (Metanome) screened by the meaning of their attributes; column names of prior work tools/src/fd_names.py (UCI documentation, HPI headers)",
            "truth_kind": "semantic screening",
            "rule": "Sigma* holds the FDs the screening judged to express a rule of the domain; it is a judgement on attribute names and documentation, not a specification. A borderline FD is unsure. Every other mined FD is labelled accidental.",
            "datasets": out}


if __name__ == "__main__":
    tools = sys.argv[1]
    for fam, doc in (("documented", documented(tools)), ("screened", screened())):
        with open(os.path.join(HERE, "truth", fam + ".json"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1, ensure_ascii=False)
        print(fam, {ds: len(s["truth"]) for ds, s in doc["datasets"].items()})
