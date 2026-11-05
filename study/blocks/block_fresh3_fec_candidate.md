# Fixed block of fresh3_fec_candidate (check by hand)

Attributes: CAND_ID, CAND_PTY_AFFILIATION, CAND_ELECTION_YR, CAND_OFFICE_ST, CAND_OFFICE, CAND_OFFICE_DISTRICT, CAND_ICI, CAND_STATUS, CAND_PCC, CMTE_NM, CMTE_DSGN, CMTE_TP, CMTE_PTY_AFFILIATION, CMTE_FILING_FREQ, ORG_TP, CONNECTED_ORG_NM, CM_CAND_ID, CMTE_ST, CMTE_ZIP, CMTE_CITY
Pool sizes: {'cand/True': 11, 'cand/False': 707, 'max/True': 11, 'max/False': 11, 'qx/True': 35156, 'qx/False': 24128}

## Block

- **b01** cand, TRUE, a(q) = 2, lhs = {CAND_PCC} -> CMTE_ZIP
  - shown: Must any two records that agree on CAND_PCC also agree on CMTE_ZIP?
  - true: CAND_PCC -> CMTE_ZIP
- **b02** cand, TRUE, a(q) = 2, lhs = {CAND_PCC} -> CMTE_PTY_AFFILIATION
  - shown: Must any two records that agree on CAND_PCC also agree on CMTE_PTY_AFFILIATION?
  - true: CAND_PCC -> CMTE_PTY_AFFILIATION
- **b03** cand, TRUE, a(q) = 2, lhs = {CAND_PCC} -> CMTE_FILING_FREQ
  - shown: Must any two records that agree on CAND_PCC also agree on CMTE_FILING_FREQ?
  - true: CAND_PCC -> CMTE_FILING_FREQ
- **b04** cand, FALSE, a(q) = 2, lhs = {CMTE_ZIP} -> ORG_TP
  - shown: Must any two records that agree on CMTE_ZIP also agree on ORG_TP?
  - false: closure of the left-hand side under the full truth is CMTE_ZIP
- **b05** cand, FALSE, a(q) = 4, lhs = {CAND_ELECTION_YR, CAND_OFFICE_ST, CMTE_NM} -> CMTE_TP
  - shown: Must any two records that agree on CAND_ELECTION_YR, CAND_OFFICE_ST and CMTE_NM also agree on CMTE_TP?
  - false: closure of the left-hand side under the full truth is CAND_ELECTION_YR,CAND_OFFICE_ST,CMTE_NM
- **b06** cand, FALSE, a(q) = 6, lhs = {CAND_ELECTION_YR, CAND_ICI, CMTE_PTY_AFFILIATION, CM_CAND_ID, CMTE_CITY} -> CONNECTED_ORG_NM
  - shown: Must any two records that agree on CAND_ELECTION_YR, CAND_ICI, CMTE_PTY_AFFILIATION, CM_CAND_ID and CMTE_CITY also agree on CONNECTED_ORG_NM?
  - false: closure of the left-hand side under the full truth is CAND_ELECTION_YR,CAND_ICI,CMTE_PTY_AFFILIATION,CM_CAND_ID,CMTE_CITY
- **b07** max, TRUE, a(q) = 3, lhs = {CAND_PTY_AFFILIATION, CAND_ELECTION_YR, CAND_OFFICE_ST, CAND_OFFICE, CAND_OFFICE_DISTRICT, CAND_ICI, CAND_STATUS, CAND_PCC, CMTE_NM, CMTE_DSGN, CMTE_TP, CMTE_PTY_AFFILIATION, CMTE_FILING_FREQ, ORG_TP, CONNECTED_ORG_NM, CM_CAND_ID, CMTE_ST, CMTE_ZIP} -> CMTE_CITY
  - shown: Must any two records that agree on all attributes except CAND_ID and CMTE_CITY also agree on CMTE_CITY?
  - true: CAND_PCC -> CMTE_CITY
- **b08** max, TRUE, a(q) = 3, lhs = {CAND_PTY_AFFILIATION, CAND_ELECTION_YR, CAND_OFFICE_ST, CAND_OFFICE, CAND_OFFICE_DISTRICT, CAND_ICI, CAND_STATUS, CAND_PCC, CMTE_NM, CMTE_DSGN, CMTE_TP, CMTE_PTY_AFFILIATION, CMTE_FILING_FREQ, ORG_TP, CONNECTED_ORG_NM, CM_CAND_ID, CMTE_ZIP, CMTE_CITY} -> CMTE_ST
  - shown: Must any two records that agree on all attributes except CAND_ID and CMTE_ST also agree on CMTE_ST?
  - true: CAND_PCC -> CMTE_ST
- **b09** max, TRUE, a(q) = 3, lhs = {CAND_PTY_AFFILIATION, CAND_ELECTION_YR, CAND_OFFICE_ST, CAND_OFFICE, CAND_OFFICE_DISTRICT, CAND_ICI, CAND_STATUS, CAND_PCC, CMTE_NM, CMTE_DSGN, CMTE_PTY_AFFILIATION, CMTE_FILING_FREQ, ORG_TP, CONNECTED_ORG_NM, CM_CAND_ID, CMTE_ST, CMTE_ZIP, CMTE_CITY} -> CMTE_TP
  - shown: Must any two records that agree on all attributes except CAND_ID and CMTE_TP also agree on CMTE_TP?
  - true: CAND_PCC -> CMTE_TP
- **b10** max, FALSE, a(q) = 4, lhs = {CAND_PTY_AFFILIATION, CAND_ELECTION_YR, CAND_OFFICE_ST, CAND_OFFICE, CAND_OFFICE_DISTRICT, CAND_ICI, CAND_STATUS, CMTE_NM, CMTE_TP, CMTE_PTY_AFFILIATION, CMTE_FILING_FREQ, ORG_TP, CONNECTED_ORG_NM, CM_CAND_ID, CMTE_ST, CMTE_ZIP, CMTE_CITY} -> CMTE_DSGN
  - shown: Must any two records that agree on all attributes except CAND_ID, CAND_PCC and CMTE_DSGN also agree on CMTE_DSGN?
  - false: closure of the left-hand side under the full truth is CAND_PTY_AFFILIATION,CAND_ELECTION_YR,CAND_OFFICE_ST,CAND_OFFICE,CAND_OFFICE_DISTRICT,CAND_ICI,CAND_STATUS,CMTE_NM,CMTE_TP,CMTE_PTY_AFFILIATION,CMTE_FILING_FREQ,ORG_TP,CONNECTED_ORG_NM,CM_CAND_ID,CMTE_ST,CMTE_ZIP,CMTE_CITY
- **b11** max, FALSE, a(q) = 4, lhs = {CAND_PTY_AFFILIATION, CAND_ELECTION_YR, CAND_OFFICE_ST, CAND_OFFICE, CAND_OFFICE_DISTRICT, CAND_ICI, CAND_STATUS, CMTE_DSGN, CMTE_TP, CMTE_PTY_AFFILIATION, CMTE_FILING_FREQ, ORG_TP, CONNECTED_ORG_NM, CM_CAND_ID, CMTE_ST, CMTE_ZIP, CMTE_CITY} -> CMTE_NM
  - shown: Must any two records that agree on all attributes except CAND_ID, CAND_PCC and CMTE_NM also agree on CMTE_NM?
  - false: closure of the left-hand side under the full truth is CAND_PTY_AFFILIATION,CAND_ELECTION_YR,CAND_OFFICE_ST,CAND_OFFICE,CAND_OFFICE_DISTRICT,CAND_ICI,CAND_STATUS,CMTE_DSGN,CMTE_TP,CMTE_PTY_AFFILIATION,CMTE_FILING_FREQ,ORG_TP,CONNECTED_ORG_NM,CM_CAND_ID,CMTE_ST,CMTE_ZIP,CMTE_CITY
- **b12** max, FALSE, a(q) = 4, lhs = {CAND_PTY_AFFILIATION, CAND_ELECTION_YR, CAND_OFFICE_ST, CAND_OFFICE, CAND_OFFICE_DISTRICT, CAND_ICI, CAND_STATUS, CMTE_NM, CMTE_DSGN, CMTE_TP, CMTE_PTY_AFFILIATION, CMTE_FILING_FREQ, ORG_TP, CONNECTED_ORG_NM, CM_CAND_ID, CMTE_ZIP, CMTE_CITY} -> CMTE_ST
  - shown: Must any two records that agree on all attributes except CAND_ID, CAND_PCC and CMTE_ST also agree on CMTE_ST?
  - false: closure of the left-hand side under the full truth is CAND_PTY_AFFILIATION,CAND_ELECTION_YR,CAND_OFFICE_ST,CAND_OFFICE,CAND_OFFICE_DISTRICT,CAND_ICI,CAND_STATUS,CMTE_NM,CMTE_DSGN,CMTE_TP,CMTE_PTY_AFFILIATION,CMTE_FILING_FREQ,ORG_TP,CONNECTED_ORG_NM,CM_CAND_ID,CMTE_ZIP,CMTE_CITY
- **b13** qx, TRUE, a(q) = 4, lhs = {CAND_PCC, CMTE_DSGN, ORG_TP} -> CM_CAND_ID
  - shown: Must any two records that agree on CAND_PCC, CMTE_DSGN and ORG_TP also agree on CM_CAND_ID?
  - true: CAND_PCC -> CM_CAND_ID
- **b14** qx, TRUE, a(q) = 5, lhs = {CAND_PTY_AFFILIATION, CAND_OFFICE_ST, CAND_PCC, CMTE_DSGN} -> CMTE_PTY_AFFILIATION
  - shown: Must any two records that agree on CAND_PTY_AFFILIATION, CAND_OFFICE_ST, CAND_PCC and CMTE_DSGN also agree on CMTE_PTY_AFFILIATION?
  - true: CAND_PCC -> CMTE_PTY_AFFILIATION
- **b15** qx, TRUE, a(q) = 6, lhs = {CAND_OFFICE_ST, CAND_PCC, CMTE_NM, CMTE_TP, CM_CAND_ID} -> CMTE_PTY_AFFILIATION
  - shown: Must any two records that agree on CAND_OFFICE_ST, CAND_PCC, CMTE_NM, CMTE_TP and CM_CAND_ID also agree on CMTE_PTY_AFFILIATION?
  - true: CAND_PCC -> CMTE_PTY_AFFILIATION
- **b16** qx, FALSE, a(q) = 4, lhs = {CMTE_FILING_FREQ, CMTE_ST, CMTE_ZIP} -> ORG_TP
  - shown: Must any two records that agree on CMTE_FILING_FREQ, CMTE_ST and CMTE_ZIP also agree on ORG_TP?
  - false: closure of the left-hand side under the full truth is CMTE_FILING_FREQ,CMTE_ST,CMTE_ZIP
- **b17** qx, FALSE, a(q) = 5, lhs = {CAND_OFFICE_DISTRICT, CMTE_NM, CMTE_FILING_FREQ, CM_CAND_ID} -> CMTE_DSGN
  - shown: Must any two records that agree on CAND_OFFICE_DISTRICT, CMTE_NM, CMTE_FILING_FREQ and CM_CAND_ID also agree on CMTE_DSGN?
  - false: closure of the left-hand side under the full truth is CAND_OFFICE_DISTRICT,CMTE_NM,CMTE_FILING_FREQ,CM_CAND_ID
- **b18** qx, FALSE, a(q) = 6, lhs = {CAND_PTY_AFFILIATION, CAND_OFFICE_ST, CAND_ICI, CMTE_NM, CM_CAND_ID} -> CMTE_ST
  - shown: Must any two records that agree on CAND_PTY_AFFILIATION, CAND_OFFICE_ST, CAND_ICI, CMTE_NM and CM_CAND_ID also agree on CMTE_ST?
  - false: closure of the left-hand side under the full truth is CAND_PTY_AFFILIATION,CAND_OFFICE_ST,CAND_ICI,CMTE_NM,CM_CAND_ID

## Fillers

- **f01** cand, TRUE, a(q) = 2, lhs = {CAND_PCC} -> CMTE_TP
  - shown: Must any two records that agree on CAND_PCC also agree on CMTE_TP?
  - true: CAND_PCC -> CMTE_TP
- **f02** cand, TRUE, a(q) = 2, lhs = {CAND_PCC} -> CONNECTED_ORG_NM
  - shown: Must any two records that agree on CAND_PCC also agree on CONNECTED_ORG_NM?
  - true: CAND_PCC -> CONNECTED_ORG_NM
- **f03** cand, FALSE, a(q) = 2, lhs = {CMTE_NM} -> ORG_TP
  - shown: Must any two records that agree on CMTE_NM also agree on ORG_TP?
  - false: closure of the left-hand side under the full truth is CMTE_NM
- **f04** cand, FALSE, a(q) = 6, lhs = {CAND_STATUS, CMTE_DSGN, CMTE_TP, CM_CAND_ID, CMTE_ST} -> CONNECTED_ORG_NM
  - shown: Must any two records that agree on CAND_STATUS, CMTE_DSGN, CMTE_TP, CM_CAND_ID and CMTE_ST also agree on CONNECTED_ORG_NM?
  - false: closure of the left-hand side under the full truth is CAND_STATUS,CMTE_DSGN,CMTE_TP,CM_CAND_ID,CMTE_ST
- **f05** max, TRUE, a(q) = 3, lhs = {CAND_PTY_AFFILIATION, CAND_ELECTION_YR, CAND_OFFICE_ST, CAND_OFFICE, CAND_OFFICE_DISTRICT, CAND_ICI, CAND_STATUS, CAND_PCC, CMTE_DSGN, CMTE_TP, CMTE_PTY_AFFILIATION, CMTE_FILING_FREQ, ORG_TP, CONNECTED_ORG_NM, CM_CAND_ID, CMTE_ST, CMTE_ZIP, CMTE_CITY} -> CMTE_NM
  - shown: Must any two records that agree on all attributes except CAND_ID and CMTE_NM also agree on CMTE_NM?
  - true: CAND_PCC -> CMTE_NM
- **f06** max, TRUE, a(q) = 3, lhs = {CAND_PTY_AFFILIATION, CAND_ELECTION_YR, CAND_OFFICE_ST, CAND_OFFICE, CAND_OFFICE_DISTRICT, CAND_ICI, CAND_STATUS, CAND_PCC, CMTE_NM, CMTE_DSGN, CMTE_TP, CMTE_PTY_AFFILIATION, CMTE_FILING_FREQ, CONNECTED_ORG_NM, CM_CAND_ID, CMTE_ST, CMTE_ZIP, CMTE_CITY} -> ORG_TP
  - shown: Must any two records that agree on all attributes except CAND_ID and ORG_TP also agree on ORG_TP?
  - true: CAND_PCC -> ORG_TP
- **f07** max, FALSE, a(q) = 4, lhs = {CAND_PTY_AFFILIATION, CAND_ELECTION_YR, CAND_OFFICE_ST, CAND_OFFICE, CAND_OFFICE_DISTRICT, CAND_ICI, CAND_STATUS, CMTE_NM, CMTE_DSGN, CMTE_TP, CMTE_PTY_AFFILIATION, CMTE_FILING_FREQ, ORG_TP, CM_CAND_ID, CMTE_ST, CMTE_ZIP, CMTE_CITY} -> CONNECTED_ORG_NM
  - shown: Must any two records that agree on all attributes except CAND_ID, CAND_PCC and CONNECTED_ORG_NM also agree on CONNECTED_ORG_NM?
  - false: closure of the left-hand side under the full truth is CAND_PTY_AFFILIATION,CAND_ELECTION_YR,CAND_OFFICE_ST,CAND_OFFICE,CAND_OFFICE_DISTRICT,CAND_ICI,CAND_STATUS,CMTE_NM,CMTE_DSGN,CMTE_TP,CMTE_PTY_AFFILIATION,CMTE_FILING_FREQ,ORG_TP,CM_CAND_ID,CMTE_ST,CMTE_ZIP,CMTE_CITY
- **f08** max, FALSE, a(q) = 4, lhs = {CAND_PTY_AFFILIATION, CAND_ELECTION_YR, CAND_OFFICE_ST, CAND_OFFICE, CAND_OFFICE_DISTRICT, CAND_ICI, CAND_STATUS, CMTE_NM, CMTE_DSGN, CMTE_TP, CMTE_PTY_AFFILIATION, CMTE_FILING_FREQ, ORG_TP, CONNECTED_ORG_NM, CMTE_ST, CMTE_ZIP, CMTE_CITY} -> CM_CAND_ID
  - shown: Must any two records that agree on all attributes except CAND_ID, CAND_PCC and CM_CAND_ID also agree on CM_CAND_ID?
  - false: closure of the left-hand side under the full truth is CAND_PTY_AFFILIATION,CAND_ELECTION_YR,CAND_OFFICE_ST,CAND_OFFICE,CAND_OFFICE_DISTRICT,CAND_ICI,CAND_STATUS,CMTE_NM,CMTE_DSGN,CMTE_TP,CMTE_PTY_AFFILIATION,CMTE_FILING_FREQ,ORG_TP,CONNECTED_ORG_NM,CMTE_ST,CMTE_ZIP,CMTE_CITY
- **f09** qx, TRUE, a(q) = 4, lhs = {CAND_PCC, CMTE_NM, CMTE_TP} -> CM_CAND_ID
  - shown: Must any two records that agree on CAND_PCC, CMTE_NM and CMTE_TP also agree on CM_CAND_ID?
  - true: CAND_PCC -> CM_CAND_ID
- **f10** qx, TRUE, a(q) = 6, lhs = {CAND_OFFICE_DISTRICT, CAND_PCC, CMTE_NM, CONNECTED_ORG_NM, CMTE_CITY} -> CMTE_FILING_FREQ
  - shown: Must any two records that agree on CAND_OFFICE_DISTRICT, CAND_PCC, CMTE_NM, CONNECTED_ORG_NM and CMTE_CITY also agree on CMTE_FILING_FREQ?
  - true: CAND_PCC -> CMTE_FILING_FREQ
- **f11** qx, FALSE, a(q) = 4, lhs = {CAND_ELECTION_YR, CMTE_NM, CM_CAND_ID} -> CMTE_TP
  - shown: Must any two records that agree on CAND_ELECTION_YR, CMTE_NM and CM_CAND_ID also agree on CMTE_TP?
  - false: closure of the left-hand side under the full truth is CAND_ELECTION_YR,CMTE_NM,CM_CAND_ID
- **f12** qx, FALSE, a(q) = 6, lhs = {CAND_ELECTION_YR, CMTE_NM, CMTE_FILING_FREQ, CM_CAND_ID, CMTE_ST} -> CMTE_TP
  - shown: Must any two records that agree on CAND_ELECTION_YR, CMTE_NM, CMTE_FILING_FREQ, CM_CAND_ID and CMTE_ST also agree on CMTE_TP?
  - false: closure of the left-hand side under the full truth is CAND_ELECTION_YR,CMTE_NM,CMTE_FILING_FREQ,CM_CAND_ID,CMTE_ST
