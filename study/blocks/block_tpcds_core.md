# Fixed block of tpcds_core (check by hand)

Attributes: ss_ticket_number, ss_quantity, ss_sales_price, i_item_sk, i_item_id, i_item_desc, i_current_price, s_store_sk, s_store_id, s_store_name, d_date_sk, d_date
Pool sizes: {'cand/True': 13, 'cand/False': 25, 'max/True': 51, 'max/False': 8, 'qx/True': 3174, 'qx/False': 562}

## Block

- **b01** cand, TRUE, a(q) = 2, lhs = {s_store_sk} -> s_store_name
  - shown: Must any two records that agree on s_store_sk also agree on s_store_name?
  - true: s_store_sk -> s_store_name
- **b02** cand, TRUE, a(q) = 2, lhs = {d_date_sk} -> d_date
  - shown: Must any two records that agree on d_date_sk also agree on d_date?
  - true: d_date_sk -> d_date
- **b03** cand, TRUE, a(q) = 3, lhs = {i_item_id, d_date} -> i_item_sk
  - shown: Must any two records that agree on i_item_id and d_date also agree on i_item_sk?
  - true: i_item_id,d_date -> i_item_sk
- **b04** cand, FALSE, a(q) = 2, lhs = {s_store_name} -> s_store_sk
  - shown: Must any two records that agree on s_store_name also agree on s_store_sk?
  - false: closure of the left-hand side under the full truth is s_store_name
- **b05** cand, FALSE, a(q) = 4, lhs = {ss_ticket_number, ss_sales_price, i_item_desc} -> i_current_price
  - shown: Must any two records that agree on ss_ticket_number, ss_sales_price and i_item_desc also agree on i_current_price?
  - false: closure of the left-hand side under the full truth is ss_ticket_number,ss_sales_price,i_item_desc,s_store_sk,s_store_id,s_store_name,d_date_sk,d_date
- **b06** cand, FALSE, a(q) = 6, lhs = {ss_quantity, ss_sales_price, i_item_desc, i_current_price, d_date} -> i_item_sk
  - shown: Must any two records that agree on ss_quantity, ss_sales_price, i_item_desc, i_current_price and d_date also agree on i_item_sk?
  - false: closure of the left-hand side under the full truth is ss_quantity,ss_sales_price,i_item_desc,i_current_price,d_date_sk,d_date
- **b07** max, TRUE, a(q) = 2, lhs = {ss_ticket_number, ss_quantity, ss_sales_price, i_item_id, i_item_desc, i_current_price, s_store_sk, s_store_id, s_store_name, d_date_sk, d_date} -> i_item_sk
  - shown: Must any two records that agree on all attributes except i_item_sk also agree on i_item_sk?
  - true: i_item_id,d_date -> i_item_sk
- **b08** max, TRUE, a(q) = 4, lhs = {ss_quantity, ss_sales_price, i_item_sk, i_item_id, i_item_desc, i_current_price, s_store_sk, d_date_sk, d_date} -> s_store_name
  - shown: Must any two records that agree on all attributes except ss_ticket_number, s_store_id and s_store_name also agree on s_store_name?
  - true: s_store_sk -> s_store_name
- **b09** max, TRUE, a(q) = 5, lhs = {ss_quantity, ss_sales_price, i_item_sk, i_item_id, i_item_desc, i_current_price, s_store_sk, s_store_id} -> s_store_name
  - shown: Must any two records that agree on all attributes except ss_ticket_number, d_date_sk, d_date and s_store_name also agree on s_store_name?
  - true: s_store_sk -> s_store_name
- **b10** max, FALSE, a(q) = 3, lhs = {ss_ticket_number, ss_quantity, ss_sales_price, i_item_desc, i_current_price, s_store_sk, s_store_id, s_store_name, d_date_sk, d_date} -> i_item_id
  - shown: Must any two records that agree on all attributes except i_item_sk and i_item_id also agree on i_item_id?
  - false: closure of the left-hand side under the full truth is ss_ticket_number,ss_quantity,ss_sales_price,i_item_desc,i_current_price,s_store_sk,s_store_id,s_store_name,d_date_sk,d_date
- **b11** max, FALSE, a(q) = 5, lhs = {ss_quantity, ss_sales_price, i_item_sk, i_item_id, i_item_desc, i_current_price, s_store_id, s_store_name} -> s_store_sk
  - shown: Must any two records that agree on all attributes except ss_ticket_number, d_date_sk, d_date and s_store_sk also agree on s_store_sk?
  - false: closure of the left-hand side under the full truth is ss_quantity,ss_sales_price,i_item_sk,i_item_id,i_item_desc,i_current_price,s_store_id,s_store_name
- **b12** max, FALSE, a(q) = 6, lhs = {ss_quantity, ss_sales_price, i_item_sk, i_item_id, i_item_desc, i_current_price, s_store_id} -> s_store_name
  - shown: Must any two records that agree on all attributes except ss_ticket_number, s_store_sk, d_date_sk, d_date and s_store_name also agree on s_store_name?
  - false: closure of the left-hand side under the full truth is ss_quantity,ss_sales_price,i_item_sk,i_item_id,i_item_desc,i_current_price,s_store_id
- **b13** qx, TRUE, a(q) = 4, lhs = {i_item_desc, s_store_sk, d_date_sk} -> s_store_name
  - shown: Must any two records that agree on i_item_desc, s_store_sk and d_date_sk also agree on s_store_name?
  - true: s_store_sk -> s_store_name
- **b14** qx, TRUE, a(q) = 5, lhs = {i_item_sk, i_item_id, i_item_desc, s_store_sk} -> s_store_id
  - shown: Must any two records that agree on i_item_sk, i_item_id, i_item_desc and s_store_sk also agree on s_store_id?
  - true: s_store_sk -> s_store_id
- **b15** qx, TRUE, a(q) = 6, lhs = {i_item_id, i_item_desc, s_store_id, s_store_name, d_date_sk} -> i_item_sk
  - shown: Must any two records that agree on i_item_id, i_item_desc, s_store_id, s_store_name and d_date_sk also agree on i_item_sk?
  - true: d_date_sk -> d_date; i_item_id,d_date -> i_item_sk
- **b16** qx, FALSE, a(q) = 4, lhs = {i_item_desc, i_current_price, s_store_id} -> s_store_name
  - shown: Must any two records that agree on i_item_desc, i_current_price and s_store_id also agree on s_store_name?
  - false: closure of the left-hand side under the full truth is i_item_desc,i_current_price,s_store_id
- **b17** qx, FALSE, a(q) = 5, lhs = {i_item_sk, i_item_desc, s_store_name, d_date_sk} -> s_store_sk
  - shown: Must any two records that agree on i_item_sk, i_item_desc, s_store_name and d_date_sk also agree on s_store_sk?
  - false: closure of the left-hand side under the full truth is i_item_sk,i_item_id,i_item_desc,i_current_price,s_store_name,d_date_sk,d_date
- **b18** qx, FALSE, a(q) = 6, lhs = {ss_sales_price, i_item_id, i_item_desc, s_store_name, d_date_sk} -> s_store_sk
  - shown: Must any two records that agree on ss_sales_price, i_item_id, i_item_desc, s_store_name and d_date_sk also agree on s_store_sk?
  - false: closure of the left-hand side under the full truth is ss_sales_price,i_item_sk,i_item_id,i_item_desc,i_current_price,s_store_name,d_date_sk,d_date

## Fillers

- **f01** cand, TRUE, a(q) = 2, lhs = {i_item_sk} -> i_current_price
  - shown: Must any two records that agree on i_item_sk also agree on i_current_price?
  - true: i_item_sk -> i_current_price
- **f02** cand, TRUE, a(q) = 3, lhs = {i_item_id, d_date_sk} -> i_item_desc
  - shown: Must any two records that agree on i_item_id and d_date_sk also agree on i_item_desc?
  - true: i_item_sk -> i_item_desc; d_date_sk -> d_date; i_item_id,d_date -> i_item_sk
- **f03** cand, FALSE, a(q) = 2, lhs = {s_store_id} -> s_store_sk
  - shown: Must any two records that agree on s_store_id also agree on s_store_sk?
  - false: closure of the left-hand side under the full truth is s_store_id
- **f04** cand, FALSE, a(q) = 6, lhs = {ss_quantity, ss_sales_price, i_item_desc, i_current_price, d_date_sk} -> i_item_sk
  - shown: Must any two records that agree on ss_quantity, ss_sales_price, i_item_desc, i_current_price and d_date_sk also agree on i_item_sk?
  - false: closure of the left-hand side under the full truth is ss_quantity,ss_sales_price,i_item_desc,i_current_price,d_date_sk,d_date
- **f05** max, TRUE, a(q) = 3, lhs = {ss_ticket_number, ss_quantity, ss_sales_price, i_item_id, i_current_price, s_store_sk, s_store_id, s_store_name, d_date_sk, d_date} -> i_item_desc
  - shown: Must any two records that agree on all attributes except i_item_sk and i_item_desc also agree on i_item_desc?
  - true: i_item_sk -> i_item_desc; i_item_id,d_date -> i_item_sk
- **f06** max, TRUE, a(q) = 5, lhs = {ss_quantity, ss_sales_price, i_item_sk, i_item_id, i_item_desc, i_current_price, s_store_id, d_date_sk} -> s_store_name
  - shown: Must any two records that agree on all attributes except ss_ticket_number, s_store_sk, d_date and s_store_name also agree on s_store_name?
  - true: s_store_sk -> s_store_name; d_date_sk -> d_date; s_store_id,d_date -> s_store_sk
- **f07** max, FALSE, a(q) = 3, lhs = {ss_ticket_number, ss_quantity, ss_sales_price, i_item_desc, i_current_price, s_store_sk, s_store_id, s_store_name, d_date_sk, d_date} -> i_item_sk
  - shown: Must any two records that agree on all attributes except i_item_id and i_item_sk also agree on i_item_sk?
  - false: closure of the left-hand side under the full truth is ss_ticket_number,ss_quantity,ss_sales_price,i_item_desc,i_current_price,s_store_sk,s_store_id,s_store_name,d_date_sk,d_date
- **f08** max, FALSE, a(q) = 4, lhs = {ss_ticket_number, ss_quantity, ss_sales_price, i_item_desc, s_store_sk, s_store_id, s_store_name, d_date_sk, d_date} -> i_current_price
  - shown: Must any two records that agree on all attributes except i_item_sk, i_item_id and i_current_price also agree on i_current_price?
  - false: closure of the left-hand side under the full truth is ss_ticket_number,ss_quantity,ss_sales_price,i_item_desc,s_store_sk,s_store_id,s_store_name,d_date_sk,d_date
- **f09** qx, TRUE, a(q) = 4, lhs = {ss_quantity, i_item_sk, i_item_desc} -> i_item_id
  - shown: Must any two records that agree on ss_quantity, i_item_sk and i_item_desc also agree on i_item_id?
  - true: i_item_sk -> i_item_id
- **f10** qx, TRUE, a(q) = 6, lhs = {ss_ticket_number, ss_quantity, i_item_id, i_item_desc, d_date} -> d_date_sk
  - shown: Must any two records that agree on ss_ticket_number, ss_quantity, i_item_id, i_item_desc and d_date also agree on d_date_sk?
  - true: d_date -> d_date_sk
- **f11** qx, FALSE, a(q) = 4, lhs = {ss_quantity, i_item_sk, s_store_id} -> s_store_name
  - shown: Must any two records that agree on ss_quantity, i_item_sk and s_store_id also agree on s_store_name?
  - false: closure of the left-hand side under the full truth is ss_quantity,i_item_sk,i_item_id,i_item_desc,i_current_price,s_store_id
- **f12** qx, FALSE, a(q) = 6, lhs = {ss_quantity, i_item_sk, i_item_desc, s_store_name, d_date} -> s_store_sk
  - shown: Must any two records that agree on ss_quantity, i_item_sk, i_item_desc, s_store_name and d_date also agree on s_store_sk?
  - false: closure of the left-hand side under the full truth is ss_quantity,i_item_sk,i_item_id,i_item_desc,i_current_price,s_store_name,d_date_sk,d_date
