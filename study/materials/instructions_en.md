# Instruction sheet (one page, handed out and shown on screen)

DRAFT 2026-10-31. The same text opens the web page (`code/ui.html`); change both together.

## What you will do

You will see a table and answer questions about its **rules**. Each question names some attributes (columns) and asks
whether two records that agree on them **must** also agree on another attribute.

A question is about every valid state of the table, not only about the ten sample rows you see. The rows only show
what the values look like. Answer

- **Yes** if the rule must always hold,
- **No** if two valid records could break it,
- **Don't know** if you cannot tell.

(Conditions E and P only.) You can open the documentation of the table at any time with the links above the questions.

There are at most about 130 questions and at most about 55 minutes of answering. You can stop at any time with the
Stop button, without giving a reason.

## Two practice questions (not part of the study)

The table Orders records for each order the name and city of its customer and the date of the order.

| Order | Name  | City       | Date    |
|-------|-------|------------|---------|
| o1    | Smith | Auckland   | 3 March |
| o2    | Smith | Auckland   | 3 March |
| o3    | Jones | Wellington | 3 March |
| o4    | Brown | Auckland   | 5 March |
| o5    | Smith | Auckland   | 5 March |

1. Must any two records that agree on **Name** also agree on **City**?
   *No. In these rows every Smith lives in Auckland, but two different customers called Smith may live in different
   cities, so the rule need not hold.*
2. Must any two records that agree on all attributes except **City** also agree on **City**?
   *Yes. Two such records have the same order, and an order belongs to one customer with one city.*

## For the experimenter (not shown)

- Answer questions about the interface only, never about the table or a rule.
- Do not mention that some questions are asked again, or that the first questions are the same for everyone.
