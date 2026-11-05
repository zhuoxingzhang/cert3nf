# Fixed block of fresh3_tpcc_customer (check by hand)

Attributes: C_D_ID, C_ID, C_LAST, C_DISCOUNT, C_CREDIT, C_STATE, C_ZIP, C_SINCE, D_NAME, D_STREET_1, D_STREET_2, D_CITY, D_STATE, D_TAX
Pool sizes: {'cand/True': 12, 'cand/False': 260, 'max/True': 12, 'max/False': 20, 'qx/True': 6072, 'qx/False': 15938}

## Block

- **b01** cand, TRUE, a(q) = 2, lhs = {C_D_ID} -> D_CITY
  - shown: Must any two records that agree on C_D_ID also agree on D_CITY?
  - true: C_D_ID -> D_CITY
- **b02** cand, TRUE, a(q) = 2, lhs = {C_D_ID} -> D_TAX
  - shown: Must any two records that agree on C_D_ID also agree on D_TAX?
  - true: C_D_ID -> D_TAX
- **b03** cand, TRUE, a(q) = 3, lhs = {C_D_ID, C_ID} -> C_CREDIT
  - shown: Must any two records that agree on C_D_ID and C_ID also agree on C_CREDIT?
  - true: C_D_ID,C_ID -> C_CREDIT
- **b04** cand, FALSE, a(q) = 2, lhs = {D_STATE} -> C_D_ID
  - shown: Must any two records that agree on D_STATE also agree on C_D_ID?
  - false: closure of the left-hand side under the full truth is D_STATE
- **b05** cand, FALSE, a(q) = 3, lhs = {C_ID, D_NAME} -> C_DISCOUNT
  - shown: Must any two records that agree on C_ID and D_NAME also agree on C_DISCOUNT?
  - false: closure of the left-hand side under the full truth is C_ID,D_NAME
- **b06** cand, FALSE, a(q) = 4, lhs = {C_DISCOUNT, C_ZIP, D_NAME} -> C_ID
  - shown: Must any two records that agree on C_DISCOUNT, C_ZIP and D_NAME also agree on C_ID?
  - false: closure of the left-hand side under the full truth is C_DISCOUNT,C_ZIP,D_NAME
- **b07** max, TRUE, a(q) = 2, lhs = {C_D_ID, C_ID, C_LAST, C_DISCOUNT, C_CREDIT, C_STATE, C_ZIP, C_SINCE, D_NAME, D_STREET_1, D_STREET_2, D_CITY, D_TAX} -> D_STATE
  - shown: Must any two records that agree on all attributes except D_STATE also agree on D_STATE?
  - true: C_D_ID -> D_STATE
- **b08** max, TRUE, a(q) = 2, lhs = {C_D_ID, C_ID, C_LAST, C_DISCOUNT, C_CREDIT, C_STATE, C_ZIP, C_SINCE, D_NAME, D_STREET_2, D_CITY, D_STATE, D_TAX} -> D_STREET_1
  - shown: Must any two records that agree on all attributes except D_STREET_1 also agree on D_STREET_1?
  - true: C_D_ID -> D_STREET_1
- **b09** max, TRUE, a(q) = 2, lhs = {C_D_ID, C_ID, C_LAST, C_DISCOUNT, C_CREDIT, C_STATE, C_ZIP, C_SINCE, D_NAME, D_STREET_1, D_CITY, D_STATE, D_TAX} -> D_STREET_2
  - shown: Must any two records that agree on all attributes except D_STREET_2 also agree on D_STREET_2?
  - true: C_D_ID -> D_STREET_2
- **b10** max, FALSE, a(q) = 2, lhs = {C_D_ID, C_LAST, C_DISCOUNT, C_CREDIT, C_STATE, C_ZIP, C_SINCE, D_NAME, D_STREET_1, D_STREET_2, D_CITY, D_STATE, D_TAX} -> C_ID
  - shown: Must any two records that agree on all attributes except C_ID also agree on C_ID?
  - false: closure of the left-hand side under the full truth is C_D_ID,C_LAST,C_DISCOUNT,C_CREDIT,C_STATE,C_ZIP,C_SINCE,D_NAME,D_STREET_1,D_STREET_2,D_CITY,D_STATE,D_TAX
- **b11** max, FALSE, a(q) = 2, lhs = {C_ID, C_LAST, C_DISCOUNT, C_CREDIT, C_STATE, C_ZIP, C_SINCE, D_NAME, D_STREET_1, D_STREET_2, D_CITY, D_STATE, D_TAX} -> C_D_ID
  - shown: Must any two records that agree on all attributes except C_D_ID also agree on C_D_ID?
  - false: closure of the left-hand side under the full truth is C_ID,C_LAST,C_DISCOUNT,C_CREDIT,C_STATE,C_ZIP,C_SINCE,D_NAME,D_STREET_1,D_STREET_2,D_CITY,D_STATE,D_TAX
- **b12** max, FALSE, a(q) = 3, lhs = {C_ID, C_LAST, C_DISCOUNT, C_STATE, C_ZIP, C_SINCE, D_NAME, D_STREET_1, D_STREET_2, D_CITY, D_STATE, D_TAX} -> C_CREDIT
  - shown: Must any two records that agree on all attributes except C_D_ID and C_CREDIT also agree on C_CREDIT?
  - false: closure of the left-hand side under the full truth is C_ID,C_LAST,C_DISCOUNT,C_STATE,C_ZIP,C_SINCE,D_NAME,D_STREET_1,D_STREET_2,D_CITY,D_STATE,D_TAX
- **b13** qx, TRUE, a(q) = 4, lhs = {C_D_ID, C_CREDIT, D_CITY} -> D_TAX
  - shown: Must any two records that agree on C_D_ID, C_CREDIT and D_CITY also agree on D_TAX?
  - true: C_D_ID -> D_TAX
- **b14** qx, TRUE, a(q) = 5, lhs = {C_D_ID, C_CREDIT, C_STATE, D_STREET_2} -> D_CITY
  - shown: Must any two records that agree on C_D_ID, C_CREDIT, C_STATE and D_STREET_2 also agree on D_CITY?
  - true: C_D_ID -> D_CITY
- **b15** qx, TRUE, a(q) = 6, lhs = {C_D_ID, C_ID, C_SINCE, D_STREET_2, D_STATE} -> C_ZIP
  - shown: Must any two records that agree on C_D_ID, C_ID, C_SINCE, D_STREET_2 and D_STATE also agree on C_ZIP?
  - true: C_D_ID,C_ID -> C_ZIP
- **b16** qx, FALSE, a(q) = 4, lhs = {C_LAST, C_ZIP, D_STATE} -> D_STREET_2
  - shown: Must any two records that agree on C_LAST, C_ZIP and D_STATE also agree on D_STREET_2?
  - false: closure of the left-hand side under the full truth is C_LAST,C_ZIP,D_STATE
- **b17** qx, FALSE, a(q) = 5, lhs = {C_LAST, C_DISCOUNT, C_CREDIT, D_STREET_2} -> D_TAX
  - shown: Must any two records that agree on C_LAST, C_DISCOUNT, C_CREDIT and D_STREET_2 also agree on D_TAX?
  - false: closure of the left-hand side under the full truth is C_LAST,C_DISCOUNT,C_CREDIT,D_STREET_2
- **b18** qx, FALSE, a(q) = 6, lhs = {C_D_ID, C_DISCOUNT, C_CREDIT, C_ZIP, D_STATE} -> C_STATE
  - shown: Must any two records that agree on C_D_ID, C_DISCOUNT, C_CREDIT, C_ZIP and D_STATE also agree on C_STATE?
  - false: closure of the left-hand side under the full truth is C_D_ID,C_DISCOUNT,C_CREDIT,C_ZIP,D_NAME,D_STREET_1,D_STREET_2,D_CITY,D_STATE,D_TAX

## Fillers

- **f01** cand, TRUE, a(q) = 2, lhs = {C_D_ID} -> D_STATE
  - shown: Must any two records that agree on C_D_ID also agree on D_STATE?
  - true: C_D_ID -> D_STATE
- **f02** cand, TRUE, a(q) = 3, lhs = {C_D_ID, C_ID} -> C_LAST
  - shown: Must any two records that agree on C_D_ID and C_ID also agree on C_LAST?
  - true: C_D_ID,C_ID -> C_LAST
- **f03** cand, FALSE, a(q) = 2, lhs = {D_NAME} -> D_TAX
  - shown: Must any two records that agree on D_NAME also agree on D_TAX?
  - false: closure of the left-hand side under the full truth is D_NAME
- **f04** cand, FALSE, a(q) = 4, lhs = {C_STATE, C_ZIP, C_SINCE} -> D_NAME
  - shown: Must any two records that agree on C_STATE, C_ZIP and C_SINCE also agree on D_NAME?
  - false: closure of the left-hand side under the full truth is C_STATE,C_ZIP,C_SINCE
- **f05** max, TRUE, a(q) = 2, lhs = {C_D_ID, C_ID, C_LAST, C_CREDIT, C_STATE, C_ZIP, C_SINCE, D_NAME, D_STREET_1, D_STREET_2, D_CITY, D_STATE, D_TAX} -> C_DISCOUNT
  - shown: Must any two records that agree on all attributes except C_DISCOUNT also agree on C_DISCOUNT?
  - true: C_D_ID,C_ID -> C_DISCOUNT
- **f06** max, TRUE, a(q) = 2, lhs = {C_D_ID, C_ID, C_LAST, C_DISCOUNT, C_CREDIT, C_STATE, C_SINCE, D_NAME, D_STREET_1, D_STREET_2, D_CITY, D_STATE, D_TAX} -> C_ZIP
  - shown: Must any two records that agree on all attributes except C_ZIP also agree on C_ZIP?
  - true: C_D_ID,C_ID -> C_ZIP
- **f07** max, FALSE, a(q) = 3, lhs = {C_ID, C_LAST, C_DISCOUNT, C_CREDIT, C_STATE, C_ZIP, C_SINCE, D_NAME, D_STREET_1, D_STREET_2, D_CITY, D_STATE} -> D_TAX
  - shown: Must any two records that agree on all attributes except C_D_ID and D_TAX also agree on D_TAX?
  - false: closure of the left-hand side under the full truth is C_ID,C_LAST,C_DISCOUNT,C_CREDIT,C_STATE,C_ZIP,C_SINCE,D_NAME,D_STREET_1,D_STREET_2,D_CITY,D_STATE
- **f08** max, FALSE, a(q) = 3, lhs = {C_D_ID, C_LAST, C_DISCOUNT, C_CREDIT, C_STATE, C_SINCE, D_NAME, D_STREET_1, D_STREET_2, D_CITY, D_STATE, D_TAX} -> C_ZIP
  - shown: Must any two records that agree on all attributes except C_ID and C_ZIP also agree on C_ZIP?
  - false: closure of the left-hand side under the full truth is C_D_ID,C_LAST,C_DISCOUNT,C_CREDIT,C_STATE,C_SINCE,D_NAME,D_STREET_1,D_STREET_2,D_CITY,D_STATE,D_TAX
- **f09** qx, TRUE, a(q) = 4, lhs = {C_D_ID, C_DISCOUNT, C_CREDIT} -> D_STATE
  - shown: Must any two records that agree on C_D_ID, C_DISCOUNT and C_CREDIT also agree on D_STATE?
  - true: C_D_ID -> D_STATE
- **f10** qx, TRUE, a(q) = 6, lhs = {C_D_ID, C_ID, C_ZIP, D_STREET_2, D_STATE} -> C_DISCOUNT
  - shown: Must any two records that agree on C_D_ID, C_ID, C_ZIP, D_STREET_2 and D_STATE also agree on C_DISCOUNT?
  - true: C_D_ID,C_ID -> C_DISCOUNT
- **f11** qx, FALSE, a(q) = 4, lhs = {C_ZIP, D_STATE, D_TAX} -> D_STREET_1
  - shown: Must any two records that agree on C_ZIP, D_STATE and D_TAX also agree on D_STREET_1?
  - false: closure of the left-hand side under the full truth is C_ZIP,D_STATE,D_TAX
- **f12** qx, FALSE, a(q) = 6, lhs = {C_ZIP, C_SINCE, D_STREET_1, D_CITY, D_TAX} -> D_NAME
  - shown: Must any two records that agree on C_ZIP, C_SINCE, D_STREET_1, D_CITY and D_TAX also agree on D_NAME?
  - false: closure of the left-hand side under the full truth is C_ZIP,C_SINCE,D_STREET_1,D_CITY,D_TAX
