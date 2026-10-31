# Fixed block of ssb_customer (check by hand)

Attributes: c_custkey, c_name, c_address, c_city, c_nation, c_region, c_phone, c_mktsegment
Pool sizes: {'cand/True': 10, 'cand/False': 12, 'max/True': 15, 'max/False': 8, 'qx/True': 216, 'qx/False': 120}

## Block

- **b01** cand, TRUE, a(q) = 2, lhs = {c_name} -> c_mktsegment
  - shown: Must any two records that agree on c_name also agree on c_mktsegment?
  - true: c_custkey -> c_mktsegment; c_name -> c_custkey
- **b02** cand, TRUE, a(q) = 2, lhs = {c_name} -> c_city
  - shown: Must any two records that agree on c_name also agree on c_city?
  - true: c_custkey -> c_city; c_name -> c_custkey
- **b03** cand, TRUE, a(q) = 2, lhs = {c_city} -> c_region
  - shown: Must any two records that agree on c_city also agree on c_region?
  - true: c_city -> c_nation; c_nation -> c_region
- **b04** cand, FALSE, a(q) = 2, lhs = {c_address} -> c_name
  - shown: Must any two records that agree on c_address also agree on c_name?
  - false: closure of the left-hand side under the full truth is c_address
- **b05** cand, FALSE, a(q) = 2, lhs = {c_phone} -> c_city
  - shown: Must any two records that agree on c_phone also agree on c_city?
  - false: closure of the left-hand side under the full truth is c_nation,c_region,c_phone
- **b06** cand, FALSE, a(q) = 2, lhs = {c_phone} -> c_mktsegment
  - shown: Must any two records that agree on c_phone also agree on c_mktsegment?
  - false: closure of the left-hand side under the full truth is c_nation,c_region,c_phone
- **b07** max, TRUE, a(q) = 2, lhs = {c_name, c_address, c_city, c_nation, c_region, c_phone, c_mktsegment} -> c_custkey
  - shown: Must any two records that agree on all attributes except c_custkey also agree on c_custkey?
  - true: c_name -> c_custkey
- **b08** max, TRUE, a(q) = 4, lhs = {c_address, c_city, c_region, c_phone, c_mktsegment} -> c_nation
  - shown: Must any two records that agree on all attributes except c_custkey, c_name and c_nation also agree on c_nation?
  - true: c_city -> c_nation
- **b09** max, TRUE, a(q) = 5, lhs = {c_address, c_city, c_region, c_mktsegment} -> c_nation
  - shown: Must any two records that agree on c_address, c_city, c_region and c_mktsegment also agree on c_nation?
  - true: c_city -> c_nation
- **b10** max, FALSE, a(q) = 3, lhs = {c_address, c_mktsegment} -> c_region
  - shown: Must any two records that agree on c_address and c_mktsegment also agree on c_region?
  - false: closure of the left-hand side under the full truth is c_address,c_mktsegment
- **b11** max, FALSE, a(q) = 3, lhs = {c_address, c_city, c_nation, c_region, c_phone, c_mktsegment} -> c_name
  - shown: Must any two records that agree on all attributes except c_custkey and c_name also agree on c_name?
  - false: closure of the left-hand side under the full truth is c_address,c_city,c_nation,c_region,c_phone,c_mktsegment
- **b12** max, FALSE, a(q) = 4, lhs = {c_address, c_nation, c_region, c_phone, c_mktsegment} -> c_city
  - shown: Must any two records that agree on all attributes except c_custkey, c_name and c_city also agree on c_city?
  - false: closure of the left-hand side under the full truth is c_address,c_nation,c_region,c_phone,c_mktsegment
- **b13** qx, TRUE, a(q) = 4, lhs = {c_name, c_address, c_phone} -> c_mktsegment
  - shown: Must any two records that agree on c_name, c_address and c_phone also agree on c_mktsegment?
  - true: c_custkey -> c_mktsegment; c_name -> c_custkey
- **b14** qx, TRUE, a(q) = 4, lhs = {c_name, c_address, c_mktsegment} -> c_phone
  - shown: Must any two records that agree on c_name, c_address and c_mktsegment also agree on c_phone?
  - true: c_custkey -> c_phone; c_name -> c_custkey
- **b15** qx, TRUE, a(q) = 5, lhs = {c_name, c_address, c_region, c_phone} -> c_mktsegment
  - shown: Must any two records that agree on c_name, c_address, c_region and c_phone also agree on c_mktsegment?
  - true: c_custkey -> c_mktsegment; c_name -> c_custkey
- **b16** qx, FALSE, a(q) = 4, lhs = {c_address, c_city, c_nation, c_phone, c_mktsegment} -> c_name
  - shown: Must any two records that agree on all attributes except c_custkey, c_region and c_name also agree on c_name?
  - false: closure of the left-hand side under the full truth is c_address,c_city,c_nation,c_region,c_phone,c_mktsegment
- **b17** qx, FALSE, a(q) = 4, lhs = {c_address, c_nation, c_region} -> c_custkey
  - shown: Must any two records that agree on c_address, c_nation and c_region also agree on c_custkey?
  - false: closure of the left-hand side under the full truth is c_address,c_nation,c_region
- **b18** qx, FALSE, a(q) = 5, lhs = {c_address, c_city, c_phone, c_mktsegment} -> c_name
  - shown: Must any two records that agree on c_address, c_city, c_phone and c_mktsegment also agree on c_name?
  - false: closure of the left-hand side under the full truth is c_address,c_city,c_nation,c_region,c_phone,c_mktsegment

## Fillers

- **f01** cand, TRUE, a(q) = 2, lhs = {c_name} -> c_custkey
  - shown: Must any two records that agree on c_name also agree on c_custkey?
  - true: c_name -> c_custkey
- **f02** cand, TRUE, a(q) = 2, lhs = {c_name} -> c_phone
  - shown: Must any two records that agree on c_name also agree on c_phone?
  - true: c_custkey -> c_phone; c_name -> c_custkey
- **f03** cand, FALSE, a(q) = 2, lhs = {c_address} -> c_city
  - shown: Must any two records that agree on c_address also agree on c_city?
  - false: closure of the left-hand side under the full truth is c_address
- **f04** cand, FALSE, a(q) = 2, lhs = {c_address} -> c_nation
  - shown: Must any two records that agree on c_address also agree on c_nation?
  - false: closure of the left-hand side under the full truth is c_address
- **f05** max, TRUE, a(q) = 3, lhs = {c_name, c_city, c_nation, c_region, c_phone, c_mktsegment} -> c_address
  - shown: Must any two records that agree on all attributes except c_custkey and c_address also agree on c_address?
  - true: c_custkey -> c_address; c_name -> c_custkey
- **f06** max, TRUE, a(q) = 5, lhs = {c_address, c_city, c_phone, c_mktsegment} -> c_region
  - shown: Must any two records that agree on c_address, c_city, c_phone and c_mktsegment also agree on c_region?
  - true: c_city -> c_nation; c_nation -> c_region
- **f07** max, FALSE, a(q) = 3, lhs = {c_address, c_city, c_nation, c_region, c_phone, c_mktsegment} -> c_custkey
  - shown: Must any two records that agree on all attributes except c_name and c_custkey also agree on c_custkey?
  - false: closure of the left-hand side under the full truth is c_address,c_city,c_nation,c_region,c_phone,c_mktsegment
- **f08** max, FALSE, a(q) = 4, lhs = {c_address, c_city, c_nation, c_region, c_phone} -> c_mktsegment
  - shown: Must any two records that agree on all attributes except c_custkey, c_name and c_mktsegment also agree on c_mktsegment?
  - false: closure of the left-hand side under the full truth is c_address,c_city,c_nation,c_region,c_phone
- **f09** qx, TRUE, a(q) = 4, lhs = {c_name, c_city, c_mktsegment} -> c_region
  - shown: Must any two records that agree on c_name, c_city and c_mktsegment also agree on c_region?
  - true: c_city -> c_nation; c_nation -> c_region
- **f10** qx, TRUE, a(q) = 5, lhs = {c_name, c_city, c_phone, c_mktsegment} -> c_region
  - shown: Must any two records that agree on c_name, c_city, c_phone and c_mktsegment also agree on c_region?
  - true: c_city -> c_nation; c_nation -> c_region
- **f11** qx, FALSE, a(q) = 4, lhs = {c_address, c_nation, c_phone} -> c_custkey
  - shown: Must any two records that agree on c_address, c_nation and c_phone also agree on c_custkey?
  - false: closure of the left-hand side under the full truth is c_address,c_nation,c_region,c_phone
- **f12** qx, FALSE, a(q) = 5, lhs = {c_address, c_city, c_region, c_phone} -> c_name
  - shown: Must any two records that agree on c_address, c_city, c_region and c_phone also agree on c_name?
  - false: closure of the left-hand side under the full truth is c_address,c_city,c_nation,c_region,c_phone
