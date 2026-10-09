# End-to-end UI test

Step 13 (D74, D76) drove the app through its real UI in Chrome, the way the HR Manager uses it: a full pass on a local container of the release, every write included, and a read-only pass on the live site. Every defect found in the app was fixed in the step with a test that fails without the fix, through the pre-commit gate, and the README's tour, the one defect outside the app, was a docs fix. This page is the record. The tests that run on every commit are listed in the README.

In short: 66 scenarios passed, 40 in the local pass, 9 in the local check of the icon and the credit and 17 on the live site, with 104 error paths and edge cases. 28 defects were found and fixed in the step: the 10 the paused run found, the 2 leads the security audit had accepted, 10 more in the pass and 6 the step's reviewers found at the close. Every defect in the app was fixed with a test that fails without the fix, and the README's tour was a docs fix. One item went to P1, search on accented capitals (D77). The live pass ran on v20, built from `2674b94`, and the close's fixes went live as v21 from `310adb2`, which opens Ship, with a read-only smoke check of 7 rows. The step closes on the commit that adds this summary.

The run was paused once, on 9 October, so that the layout and Help (step 12, D75) could be built first. Nothing from the paused run was reused: the pass below ran again on the final screens. The paused run's findings are kept under Found and fixed, marked as found before the layout change.

## Environment

| Item | Value |
| --- | --- |
| Date | 9 October 2026: the local pass from about 13:00 to 19:30 IST, the local check of the icon and the credit at about 20:25, the live pass from 20:44 to 20:50 IST |
| Driver | Claude Code (claude-opus-5-5) through the Claude in Chrome tools, extension 1.0.99, site access for localhost:8000 and acme.nutanprabhat.dev only |
| Browser | Chrome 154 on macOS, a 1512 by 982 screen at device pixel ratio 2 |
| Local target | `docker compose` on http://localhost:8000, the seeded database of 10,000 on staff and 5,000 leavers from seed 42, `NUM_PROXIES` 0 |
| Commits | the pass began on `e6db3bc` (part A and the owner's helper text), and each defect it found was fixed and rebuilt into the container as it went, `c6f36c9` and then `0d22453` (image `6a2389080921`) for the first reset and base import. The error paths below ran on `5f2106e` (image `165ef1a459dc`), which holds the four changes made after the first report, and the second reset closed them. `5e95a51`, found in that round, was rebuilt (image `62304b2d1713`) and checked last, on the seed the container rebuilt on start once the database was empty. That re-seed behind a deliberate reset was itself a defect, fixed in `57734ec` (D79): an emptied database now stays empty across restarts, which its tests cover and no restart in the browser has re-run. The reload after a deploy (`58fc79a`) is covered by its tests alone, see Not covered. The close's fixes, `bfb386f` to `70df14b`, came after release v20 and are covered by their tests, see Not covered. The icon and the credit (`dffa429`, `2674b94`) were checked on a local container of `2674b94`, see Local check of the icon and the credit |
| Window sizes | 1280 by 720 CSS pixels for the pass, 1280 by 680 for the first scenarios while the screen was shorter, 1024 by 768, and 1280 by 720 at 200% zoom, which is 640 by 360 |
| Sign-in | the HR Manager, signed in by the owner in the tab whenever a session was needed. No password was typed, read or kept by Claude Code. Deliberately wrong passwords were typed on localhost alone, with the owner's leave, for the login and reset refusals |
| Live target | https://acme.nutanprabhat.dev, read-only, see Live pass |
| Live release | v20, deployed by the owner on 9 October from `2674b94`, image `registry.fly.io/acme-salary:deployment-01M4GK3ER2Y50HP48NXG8TAKK1` |

## What is built

Page by page against SPEC section 10, as the pass found it.

| Page | What it does | SPEC |
| --- | --- | --- |
| Login | Email and password, the way back to the page asked for, the refusals and the throttle message, its own tab title, the builder's credit under the card | F8 (D80) |
| Dashboard | The key figures and nine cards under three headings over a period, country, department, currency and Include exited, each card's own control, every card exported as CSV, Excel or JSON, figures withheld for groups under five or twenty with the reason, the filter bar kept in view, a link to the Help answer on hidden figures | F5, F6, section 9 |
| Employees | The server-side directory of ten rows a page (10, 20 or 50), filters, search, sort, Go to page, the export, a pencil to open each employee, everything in the URL | F4, F6 |
| Employee page | The current record with its lines and totals, the pay history with scheduled and cancelled revisions, the audit trail on the Audit tab, Edit, Add revision, Mark exited | F3, F7 |
| New employee | Identity and the country's pay components, the error summary and the server's refusals | F3 |
| Imports | The template, the drop zone, every batch newest first | F1 |
| Import review | Counts, the message slot, Skip, the status filter, search, Approve and Discard behind their dialogs and the busy dialog | F1, F2 |
| Demo data | Seven sample files built from the live data and the reset that empties the database behind the password and RESET | F9 |
| Help | How the app works in six steps and twelve questions | section 10 (D75) |
| Every page | ACME's tab icon, and at the nav's foot the builder's credit opening nutanprabhat.dev in a new tab | D80 |

A global audit page, every change across employees in one list, is P1 (SPEC F7). Today each employee's changes are on the Audit tab of their page.

## The pass

All on localhost unless the row says otherwise. Result is Pass where the app did what SPEC and DESIGN say, and names the commit where the pass found a defect, fixed and checked again.

| # | Area | Steps | Expected | Observed | Result |
| --- | --- | --- | --- | --- | --- |
| 1 | Session | Open `/` signed out | The login page | `/login` | Pass |
| 2 | Session | Open `/employees/17?tab=history` signed out, then sign in | The login with the way back, then that page | `next` kept, the HR Manager landed on that employee | Pass |
| 3 | Session | Sign out from Help | The login page named as such | The tab kept "Help · ACME Salary" | Fixed, `c6f36c9` |
| 4 | Dashboard | Open the default view | Last 12 months, 10,000 on staff, October 2026 rates | As expected | Pass |
| 5 | Dashboard | Last FY, then Custom | The period's dates, Custom starting from them, kept in the URL | As expected. Last FY names September 2026 rates (D22, by design) | Pass |
| 6 | Dashboard | India, Local, then India to Germany, then Germany and the United States | INR, then EUR kept, then USD | As expected | Pass |
| 7 | Dashboard | Include exited, the trend's Headcount, the gender card's Bonus, then reload | Captions where Include exited does not apply, controls kept after the reload | As expected | Pass |
| 8 | Dashboard | Singapore and Legal | Figures withheld with their reasons | "fewer than 5 people", "fewer than 20 people", each with its reason | Pass |
| 9 | Dashboard | Export payroll by country as CSV, Excel and JSON | Six rows each, the filters in the JSON | As expected | Pass |
| 10 | Dashboard | Why are some figures hidden? | Help opens on that answer, focused | As expected | Pass |
| 11 | Dashboard | Scroll at 1280 by 720 | The filter bar stays at the top of the page | Sticky and flush | Pass |
| 12 | Employees | Open the directory | Ten rows, 505 px, the Designation helper on one line | As expected | Pass |
| 13 | Employees | Search `acme-1` | "1 employee matches" | As expected | Pass (A2) |
| 14 | Employees | Gross min and max, a 20 rows page and a sort, then Clear filters | Filters gone, sort and page size kept | As expected | Pass (A3) |
| 15 | Employees | A link with 100 rows a page | Opens at 10 | As expected | Pass |
| 16 | Employees | Go to page 99 on five pages | The last page | Page 5 | Pass |
| 17 | Employees | A click on a row, then the pencil | Nothing, then the employee | As expected | Pass |
| 18 | Employees | Netherlands, level 6, export CSV, Excel and JSON | 46 rows, the filters in the JSON | As expected | Pass |
| 19 | Employee page | Open ACME-1, the History and Audit tabs | The record, its lines, the history, the audit trail | As expected | Pass |
| 20 | Employee page | Add a revision for 1 January 2027, then cancel it | Saved as scheduled, then marked cancelled | As expected | Pass |
| 21 | Employee page | Edit the designation | Saved and shown | As expected | Pass |
| 22 | Employee page | Mark ACME-2 exited on 31 October 2026 | The last day shown, the exit scheduled | As expected | Pass |
| 23 | New employee | Create one in India with three lines | Created as ACME-15001, its page opened | As expected | Pass |
| 24 | Imports | newhires.xlsx | 500 valid creates, applied | 500 created | Pass |
| 25 | Imports | diwali-bonus.xlsx | 1,000 revisions, applied | 1,000 revised, the notice read "1000 revised" | Fixed, `f0b589e` |
| 26 | Imports | april-raises.xlsx, then the same file again | 1,000 scheduled revisions, then 1,000 No-op | As expected, the No-op chip shown, the second batch discarded | Pass (A5) |
| 27 | Imports | promotions.xlsx | 200 rows that change identity and pay, applied | 200 revised. An identity and pay change counts as a revision (by design) | Pass |
| 28 | Imports | exits.xlsx with one row skipped | 99 applied | 99 updated, 1 skipped | Pass |
| 29 | Imports | A sheet lowering one gross and holding a level 9 row | A warning on the first, an error blocking Approve, Show them, Skip, Approve | "gross falls from 211,902.00 to 162,000.00 EUR", then as expected | Pass |
| 30 | Imports | Approve and Discard | Their dialogs, the busy dialog while the server works | As expected | Pass |
| 31 | Worst case | Import `docs/testing/worst-case.xlsx`, made by `docs/testing/make_worst_case.py` | Five creates, one warning | As expected | Pass |
| 32 | Worst case | The five employees in the directory, on their pages and on the dashboard at 1280 by 720, 1024 by 768 and 200% | Nothing cut that has no hover, no sideways scroll above 1024 px | The Code column cut ACME-15502 to "ACME-155…" | Fixed, `2304bb2` |
| 33 | Keyboard | Tab through the directory and the dashboard, open a menu with Enter | A sensible order and every control reachable | As expected. Focus starts on the page, so the nav is behind it with Shift+Tab (D75) | Pass |
| 34 | Help | Open Help, then `/help#%` | Six steps, twelve questions, no crash | As expected | Pass |
| 35 | Windows | 1280 by 720 | No window scroll, grids at ten rows | Directory 505 px, main scrolls 75 px, review 520 px | Pass |
| 36 | Windows | 1024 by 768 | No window scroll | Directory and review 520 px with their sideways bars, the filter bar on three lines | Pass |
| 37 | Windows | 200% zoom | Sideways scroll alone below 1024 px (D75) | The window scrolls 384 px sideways, nothing else overflows, the filter bar no longer sticks | Pass |
| 38 | Container | Stop the container with the app open, then start it | The connection message with Retry, the session kept, then recovery | As expected. A page whose code had not loaded showed the error page until a full reload, which its Reload gave | Pass. The same failure after a deploy is handled by `58fc79a`, covered by its tests |
| 39 | Demo data | Empty the database with the owner's password and RESET | Everything emptied, the Imports page says what to do next | As expected | Pass |
| 40 | Demo data | Download base-15000.xlsx and import it | 15,000 creates, the seed's figures back | Staged in 7 s, applied in about 10 s, 10,000 on staff, USD 969M, mean 87,095 and median 62,329 as on the seed | Pass |

## Error paths and edge cases

| # | Trigger | Message or state shown | Where | Result |
| --- | --- | --- | --- | --- |
| 1 | Sign in with both fields empty | "Enter your email address", "Enter your password" | Login | Pass |
| 2 | A wrong password | "Email or password is wrong." | Login | Pass |
| 3 | A sixth attempt within the minute | "Too many attempts. Wait a minute and try again." | Login | Pass |
| 4 | Chrome filling a saved password into the login | The form submitted with it. The owner removed the saved password, the form then opened empty and never signed itself in | Login | Not a defect of the app |
| 5 | `?country=XX` | "Unknown country_code: XX" once, under the bar, with Clear filters, in place of the cards | Dashboard | Pass (A1) |
| 6 | `?period=custom&from=2026-02-31` | Last 12 months, the URL replaced, "This link's period could not be read, so the dashboard shows the last 12 months." | Dashboard | Pass (A5) |
| 7 | A custom From of 1 January 2019 | "From must be on or after 1 Apr 2020.", the last valid period kept | Dashboard | Pass |
| 8 | Nobody on file and no filter set | "No employees yet. Import a spreadsheet on the Imports page, or use the sample files on Demo data." with both pages linked, a filtered view keeping "No one matches these filters today. Clear a filter." | Dashboard | Fixed, `52efca1`, seen after the second reset |
| 9 | 21 titles in Designation | "designation accepts at most 20 titles" under the field, the grid kept | Employees | Pass (A1) |
| 10 | Gross min 900,000 above Gross max 100,000 | "Gross min is above Gross max" under the two fields | Employees | Pass (A5) |
| 11 | `?page=5000` | The last page, the URL replaced, no message | Employees, the import review, Imports | Fixed, `0d22453` (D77) |
| 12 | `/employees/999999` and `/employees/abc` | "This employee does not exist. Go back to the directory." | Employee page | Pass |
| 13 | `/nowhere/at/all` | "Page not found" inside the frame | Any | Pass |
| 14 | `/imports/999999` | "This import does not exist. Go back to the imports." | Import review | Pass |
| 15 | A revision dated before the latest record | "effective_from must be after 2026-04-01 (latest record)" | Revision dialog | Pass |
| 16 | An email that is not one | "email is not a valid address" | Edit dialog | Pass |
| 17 | An exit before joining | "last_date precedes joining_date" | Exit dialog | Pass |
| 18 | A new employee with nothing filled in | The summary of every missing field, focused | New employee | Fixed, `414c044` |
| 19 | A base salary of -5000 | "Enter an amount like 1450000 or 1450000.50" | New employee | Pass |
| 20 | An email already on file | "email already belongs to ACME-15001" | New employee | Pass |
| 21 | An error row in a batch | Approve off, "1 row has errors. Skip it or fix the spreadsheet and upload again." with Show them | Import review | Pass |
| 22 | The same scheduled revisions twice | Every row No-op, the chip reading No-op | Import review | Pass (A5) |
| 23 | Five worst-case rows: 120 character name, 254 character email, 80 character designation, 32 character legacy code, amounts at 9,999,999,999.99 | Created, cut text shown whole on hover, the gross warning above ten times the median | Import, directory, employee page, dashboard | Pass |
| 24 | Aleksandra Wiśniewska-Kowalczyk, J Okafor, अनन्या शर्मा, 陈美玲 | Shown and found by search in lower case | Directory | Pass, see the limit below |
| 25 | `reset` typed in lower case | Empty the database stays off | Reset dialog | Pass |
| 26 | A wrong password with RESET | "password did not match", nothing deleted | Reset dialog | Pass |
| 27 | The container stopped | "Could not load employees. Check your connection and try again." with Retry, the same on every dashboard card and on Imports, the session kept | Every page | Pass |
| 28 | A page's code missing, as after a deploy | The page reloads once onto the new build, and the error page with Reload if that fails too | Any page | Fixed, `58fc79a`, covered by its tests alone (see Not covered) |
| 29 | A batch left in review when the database is emptied | "This import does not exist. Go back to the imports." | Import review | Pass |
| 30 | The database empty | "The database is empty. Import base-15000.xlsx to start.", the generated sample files off with "Import the base file first." | Imports, Demo data | Pass |

The second round walked SPEC section 7's rule table and section 8's refusals row by row, on localhost through the UI. The sheets it used are in `docs/testing/errors/`, made by `cd backend && uv run python ../docs/testing/make_error_sheets.py` from `sample-data/base-15000.xlsx`, so they fit a database emptied on Demo data and given the base import. What could not be produced through the UI is under Not covered with the test that covers it.

### Uploads refused before any row is read

| File | Shown in the busy dialog, with Close | Result |
| --- | --- | --- |
| `not-a-sheet.txt` | "file must end in .xlsx or .csv, got not-a-sheet.txt" | Pass |
| `text-renamed.xlsx`, text named `.xlsx` | "file is not a readable .xlsx workbook; save it again from Excel and upload it" | Pass |
| `empty.xlsx`, a workbook with no rows | "file has no header row" | Pass |
| `missing-column.xlsx` | "Missing required column: country_code" | Pass |
| `column-twice.xlsx` | "email appears twice in the header; remove one" (D54) | Pass |
| `two-code-columns.xlsx`, EmployeeID and Emp ID | "EmployeeID and Emp ID could both be the legacy code; rename the right one to legacy_code" (D54) | Pass |
| `latin1.csv` | "file is not UTF-8" | Pass |

### Section 7's row rules, from `row-rules.xlsx`

One sheet of 39 rows, staged as 32 errors, 5 warnings, one No-op and one valid row, each row drawing out one rule. The batch's message slot gave the blocker and "Ignored unknown column: Remarks".

| Rule | Message on the row | Result |
| --- | --- | --- |
| A blank legacy_code | "legacy_code is required" | Pass |
| A blank required cell (D56) | "designation is required" | Pass |
| A legacy_code of 33 characters | "legacy_code is longer than 32 characters" | Pass |
| A cell one character over its column (D55) | "full_name is longer than 120 characters" | Pass |
| A cell of 300 characters (D68) | "designation is longer than 80 characters", the cell kept to 256 characters (see Not covered) | Pass |
| A legacy_code twice | "Duplicate legacy_code in rows 7 and 8" on both | Pass |
| An email twice | "Duplicate email in rows 9 and 10" on both | Pass |
| A malformed email | "email is not a valid address" | Pass |
| An email on file | "email already belongs to ACME-1" | Pass |
| An unknown country | "Unknown country_code: XX" | Pass |
| A matched employee in another country | "country change is not supported by import", with each component that country lacks | Pass |
| An unknown department | "Unknown department: Growth" | Pass |
| Level 9 | "level must be between 1 and 6" | Pass |
| An unknown gender | "gender must be one of female, male, other, undisclosed" | Pass |
| A bad date | "joining_date is not a valid date: 31/02/2024" | Pass |
| A date past 2100 (D53) | "last_date must be on or before 2100-12-31, got 9999-12-31" | Pass |
| A last day before joining | "last_date precedes joining_date" | Pass |
| A joining date moved past the first record (D45) | "joining_date is after the first record (effective 2015-01-18)" | Pass |
| A last day cleared for a leaver | "clearing last_date is not supported by import" | Pass |
| An effective date before joining | "effective_from precedes joining_date" | Pass |
| An effective date not after the latest record | "effective_from must be after 2015-02-02 (latest record)" | Pass |
| Amounts changed with no effective date | "effective_from is required when amounts change" | Pass |
| A component the country lacks | "HRA is not a component for US" | Pass |
| A negative amount | "BASE must be a non-negative number, got -5000" | Pass |
| A comma as the decimal separator | "use a dot as the decimal separator, got 1.200.000,50" | Pass |
| Three decimals | "BASE has more than 2 decimal places" | Pass |
| A blank BASE | "BASE is required" | Pass |
| BASE below 10 | "BASE must be at least 10.00, got 5.00" | Pass |
| A line over its bound | "HRA must be at most 9,999,999,999.99, got 12,000,000,000.00" | Pass |
| A negative bonus | "bonus_annual must be a non-negative number, got -1" | Pass |
| Deductions over gross, a deduction over BASE | warnings "deductions exceed gross", "TAX 1,500,000.00 is above BASE 600,000.00" | Pass |
| A bonus over BASE | warning "bonus_annual 1,500,000.00 is above BASE 1,000,000.00" | Pass |
| Gross under the country minimum | warning "gross 300,000 INR is below the India minimum 400,000" | Pass |
| Gross over ten times the median | warning "gross 60,560,000 INR is above ten times the India median 2,222,441.50" | Pass |
| A revision that lowers gross (D72) | warning "gross falls from 150,329.00 to 130,329.00 EUR" | Pass |
| A row identical to the record | No-op, "No changes, row will be skipped on apply" | Pass |
| A new employee with no effective date | "effective_from defaulted to joining_date 2024-03-01" | Pass |

### At approve, and around it

| Trigger | Shown | Result |
| --- | --- | --- |
| A revision for a leaver, alone in `exited-revision.xlsx` | "no revision after the exit on 2025-09-19" on the row | Pass |
| `legacy-taken-a.xlsx` and `legacy-taken-b.xlsx` staged, the first approved, then the second (D24) | "Nothing was applied", the row re-marked "legacy_code E2E-TAKEN now belongs to ACME-15001; upload the sheet again" | Pass |
| `changed-since-upload.xlsx` staged as an update, then the employee's pay revised in the UI effective today (D57) | "Nothing was applied", the row re-marked "ACME-16 changed since this sheet was uploaded; upload the sheet again" | Pass |
| `exit-with-scheduled.xlsx` after a revision for 1 April 2027 was scheduled in the UI | "scheduled revision on 2027-04-01 must be cancelled before exit" on the row | Pass |
| A discarded batch's URL opened again | "This batch was discarded. Nothing in it was applied.", Approve, Discard and Skip off | Pass |

### Employee page and new employee

| Trigger | Shown | Result |
| --- | --- | --- |
| A revision with BASE 0 | "BASE must be at least 10.00, got 0.00" | Pass |
| A line and a bonus over their bounds | "HRA must be at most 9,999,999,999.99, got 12,000,000,000.00", "bonus_annual must be at most 9,999,999,999.99, got 12,000,000,000.00" | Pass |
| An amount with three decimals | "Enter an amount like 1450000 or 1450000.50", before anything is sent | Pass |
| A revision on the latest record's date | "effective_from must be after 2015-01-02 (latest record)" | Pass |
| A revision before joining | "effective_from precedes joining_date" | Pass |
| A revision past 2100 | "effective_from must be on or before 2100-12-31, got 2101-01-01" | Pass |
| A note of 1,001 characters | "Use 1,000 characters or fewer", before anything is sent | Pass |
| A bonus and a tax above BASE | saved, "Check it: bonus_annual 7,000,000.00 is above BASE 6,500,000.00; TAX 7,000,000.00 is above BASE 6,500,000.00." | Pass |
| A revision for a leaver | "no revision after the exit on 2025-09-19", shown with the key "detail" in front | Fixed, `5e95a51` |
| An exit while a revision is scheduled | "scheduled revision on 2027-04-01 must be cancelled before exit", shown with the key "detail" in front | Fixed, `5e95a51` |
| An exit before the current record | "last_date precedes the current record (effective 2026-10-09)" | Pass |
| An exit before pay starts (D50) | the exit saved, version 1 cancelled | Pass |
| The joining date moved past the first record (D45) | "joining_date is after the first record (effective 2026-11-01)" | Pass |
| An exit dated today | saved, the employee still active today, Mark exited gone | Pass |
| A new employee joining on 1 January 2101 | "joining_date must be on or before 2100-12-31, got 2101-01-01" | Pass |

### Dashboard and directory

| Trigger | Shown | Result |
| --- | --- | --- |
| `?department=growth` | "Unknown department: growth" with Clear filters, in place of the cards | Pass |
| A custom From after To | "From must be on or before To.", the last valid period kept | Pass |
| A custom range in 2027 | accepted (D70), the state on 31 December 2027 | Pass |
| Singapore and Legal, Pay gap | "fewer than 5 women" | Pass |
| Legal, By level | "fewer than 5 men" on United States L1 and L4, "fewer than 5 women and fewer than 5 men" on Singapore's levels | Pass |
| Singapore and Legal over April to December 2020 | Spent in period withheld, a dash in place of the figure, "shown when each day has 5 people or more" | Pass |
| The salary distribution exported there as CSV | one row, its headcount of 5, "fewer than 20 people" | Pass |
| A search that finds no one | "0 employees match", "No employees match these filters. Clear a filter or change the search." | Pass |

### Demo data

| Trigger | Shown | Result |
| --- | --- | --- |
| Empty the database confirmed | the confirm dialog gives way to "Emptying the database…" with no buttons, so nothing can cancel it once confirmed | Pass |
| The note on the base file | names the trend, the bridge and Spent in period | Pass (`a006e96`) |

A known limit, listed under P1 (D77): search ignores case only for ASCII letters, as SQLite's matching does. "wiśniewska" and "müller" find their names. "WIŚNIEWSKA", a capital typed on a non-ASCII letter, does not find Wiśniewska.

## By design

- After a reset and the base import, Spent in period reads USD 924.2M against the seed's 892.7M. The base file holds each employee's current record alone, and a query on the container confirmed it: 15,000 employees, 15,000 live records, one each, every one starting on its joining date. So today's pay is counted back to joining, as D72 designed. The Demo data note says so beside the trend and the bridge (`a006e96`).
- A period that ends before September 2026 is converted at September 2026's rates, the earliest kept (D22). Help says so (`1a30625`).
- A cancelled revision shows "Cancelled on … by …" in its note column, in place of the note.
- A row of promotions.xlsx that changes identity and pay at once counts as revised.
- Focus moves to the page on each navigation, so Tab starts in the page and the nav is reached with Shift+Tab (D75).
- A custom period in the future is accepted to 2100 (D70), and Spent in period then reads the pay on file carried forward.
- An exit dated today leaves the employee active that day, since the last day is worked.
- A scheduled revision does not change the current record, so a sheet staged before it applies as it was staged. D57's message needs the current pay to change. A staged row with no effective date that would need one is refused with "effective_from is required when amounts change" instead.
- Help names the Audit tab and says that a period ending before September 2026 is converted at September 2026's rates (`1a30625`).

## Found and fixed

Found in the paused run, before the layout change (step 12, D75), and fixed in part A:

| Finding | Fix |
| --- | --- |
| A filter the API refuses on the dashboard (D58) showed "Could not load" on all ten cards, each retried | `3c6e2a5`, the API's words once under the bar, no 4xx retried |
| More than 20 titles in Designation showed "Could not load employees" | `3c6e2a5`, the message on the field |
| One result read "1 employee match" | `e513960` |
| Cleared gross filters came back with the next filter change, seen once | `764e216`, every URL updater builds from the latest URL, and a draft is dropped when its value changes from outside |
| An unreadable period link fell back to the last 12 months without a word | `5afa327`, the URL replaced and one line saying so |
| Gross min above Gross max gave the empty state alone | `5afa327`, "Gross min is above Gross max" |
| Designation applies on Enter, which nothing said | `5afa327`, the helper, worded by the owner in `e6db3bc` |
| The README tour named exit as a review action | `832b3b0` |
| A page that failed to render showed the router's page with its stack | `0e44569`, the app's own page in the frame |
| The review's action chip read noop | `5afa327`, No-op |

Two leads the security audit had accepted were closed in part A as well: a password change now ends every earlier session (`0fa13e0`) and no formula can start after a semicolon in a CSV cell (`e679b0d`).

Found in this pass and fixed:

| Finding | Fix |
| --- | --- |
| On a new employee's first failed submit the error summary did not take focus and sat out of view | `414c044` |
| The directory's Code column cut five digit codes | `2304bb2` |
| An applied batch's counts read 1000, not 1,000 | `f0b589e` |
| After Sign out the login tab kept the last page's title | `c6f36c9` |
| A page past the last showed the connection message | `0d22453` (D77) |
| A 409's message read "detail scheduled revision on 2027-04-01 must be cancelled before exit", the response's key on screen | `5e95a51` |
| A restart after Empty the database seeded the demo again behind the reviewer | `57734ec` (D79), covered by its tests, no restart re-run in the browser |
| An empty dashboard with no filter said to clear a filter | `52efca1` (D78) |
| A page whose code was gone, as after a deploy, stayed on the error page | `58fc79a` (D78) |
| The app shipped no favicon, so the tab showed a cached icon or a blank globe, found by the owner | `dffa429` (D80) |

Found by the step's four reviewers at the close and fixed, each with a test that fails without the fix:

| Finding | Fix |
| --- | --- |
| A formula after a separator inside a CSV cell, a line break, comma or tab, as in "Ann" then "X,=1+1" on the next line, began a cell for a reader that ignores quotes, found by the security reviewer in two rounds | `bfb386f` and `4ed3004`, the owner's choices: the writer quotes a formula after a comma, semicolon, tab or line break, and all of them stay allowed in names (D76) |
| A link past the last page of a list that had shrunk was sent first to a page that was gone too, by page 1's cached count, found by the code reviewer | `d2318ff`, page 1's own fresh count only |
| A refresh token from before a password change still rotated, its access tokens each refused, found by the security reviewer | `97819e6`, the refresh answers 401 |
| `make_import_file`'s CSV files escaped a formula only at a cell's start, found by the code reviewer | `e33663a`, the exports' whole escape |
| A refused country, as with `currency=local` and several countries, showed under the bar, not on its field, found by the spec checker | `3288916`, Department wired the same way |
| After Empty the database and a fresh import, the boot seed said the database was emptied, found by the spec checker | `46dfd9c` (D79) |
| Outside the count, a regression the close itself made: `46dfd9c` had `seed_data` import the demo services, which import from `seed_data`, so `seed_data` and `reset_demo` failed to load and the boot would have stopped. The gate passed it, since the tests import the demo services first. Found by the spec checker before any push | `0142ab1`, with a test that loads each command in a fresh process, as the boot does |

## Not covered

| What | Why | Covered by |
| --- | --- | --- |
| The reviewers' fixes at the close (`bfb386f`, `4ed3004`, `d2318ff`, `97819e6`, `e33663a`, `3288916`, `46dfd9c`, `0142ab1`) | Found after the live pass. The smoke check on v21 saw the boot, the page past the last, the gross check, the CSV and the titles, and the rest cannot be produced read-only through the UI | `backend/tests/exports/test_writers.py` (`test_csv_puts_a_single_quote_after_a_separator_a_formula_start_follows`), `backend/tests/security/test_exports_csv_line_break_split_formula.py` (`test_imported_text_cannot_start_a_formula_cell_when_the_csv_is_split_without_quotes`), `backend/tests/seed/test_commands_load.py` (`test_the_command_loads_in_a_fresh_process`), `frontend/src/pages/Employees.test.tsx` (`counts the last page from a fresh page 1 when the list shrank, not the cached one (D77)`), `frontend/src/components/grid/usePastLastPage.test.ts` (`waits for a count page 1 fetched itself, so a cached count of a list that shrank never sends it back (D77)`), `backend/tests/accounts/test_services.py` (`test_refresh_session_refuses_a_token_from_before_a_password_change`), `backend/tests/imports/test_make_import_file.py` (`test_a_csv_cell_takes_the_exports_escape_after_a_semicolon_too`), `frontend/src/pages/Employees.test.tsx` (`shows a refused %s under its field, in the API's words (D76)`), `backend/tests/seed/test_seed.py` (`test_if_empty_says_employees_exist_once_the_emptied_database_is_filled_again`) |
| A session running out after 12 hours, and a refresh token reused | Too long to wait for in a pass | `backend/tests/accounts/test_api.py` (`test_refresh_keeps_the_session_end_and_caps_the_access_token`, `test_a_reused_refresh_token_ends_every_session`), `frontend/src/api/client.test.ts` (`refreshes once for two concurrent 401s and retries both requests`, `ends the session and calls the handler when the refresh is refused`) |
| A password change ending live sessions | Changing the HR Manager's password is the operator's step | `backend/tests/accounts/test_api.py` (`test_a_password_change_ends_every_earlier_session_and_a_fresh_login_works`), `backend/tests/security/test_accounts_password_change_keeps_refresh_token_valid.py` (`test_a_password_change_ends_the_session_of_an_earlier_refresh_token`) |
| The reset's throttle of five an hour | It would lock the reset for an hour | `backend/tests/demo/test_api.py` (`test_the_reset_is_throttled_on_its_own_scope_five_an_hour`) |
| An approve cut by the proxy, a failed approve, an approve refused by the re-check | They need a failing server | `frontend/src/pages/ImportReview.test.tsx` (`keeps waiting through a cut approve until the batch leaves review`, `shows what made a failed approve fail`, `shows why an approve was refused, with the rows the re-check marked`) |
| A CSV opened in Excel set to split on semicolons | No Excel on the machine | `backend/tests/exports/test_writers.py` (`test_csv_puts_a_single_quote_after_a_semicolon_a_formula_start_follows`), `backend/tests/security/test_exports_csv_semicolon_split_formula.py` (`test_imported_text_cannot_start_a_formula_cell_when_the_csv_is_split_on_semicolons`) |
| A screen reader | Not run | Every field labelled, checked in each page's test with `expectEveryFieldLabelled`, such as `frontend/src/pages/Employees.test.tsx` (`labels every filter and the search`) |
| The reload once onto a new build after a deploy (`58fc79a`) | Only a tab already running a build with the handler meets it, and the live site has none until this deploy | `frontend/src/lib/preloadRecovery.test.ts` (`never reloads twice, leaving the error page with its Reload`, `may reload again once a page has loaded since, for the next deploy`, `leaves the error to the page when storage is refused, so it cannot loop`) and `frontend/src/App.test.tsx` (`reloads once onto the new build when a chunk fails to load (D78)`, `clears the reload guard once a navigation settles, so a later deploy reloads again`) |
| The busy dialog's line after 20 seconds | A local approve takes about 10 s | `frontend/src/components/busy/BusyProvider.test.tsx` (`counts the seconds, says why it may be slow after 20 s, warns before the page is left, and closes on the result`) |
| A cell kept as a 256 character prefix and echoed as 64 (D56, D68) | The cut sits in a column off screen in the review grid | `backend/tests/imports/test_staging.py` (`test_a_long_cell_is_kept_as_a_256_character_prefix_and_echoed_as_64`) |
| A last day before the current record, by import | Seen through the exit dialog instead | `backend/tests/compensation/test_validators.py` (`test_last_date_before_the_current_record`) |
| An upload over 10 MB | A browser upload of 10 MB was not built | `backend/tests/imports/test_api.py` (`test_an_upload_over_ten_megabytes_is_a_413_before_it_is_read`), `frontend/src/pages/Imports.test.tsx` (`refuses a file over 10 MB without sending it`) |
| More than 15,000 data rows | As above | `backend/tests/imports/test_parser.py` (`test_more_than_fifteen_thousand_data_rows_are_refused_with_the_true_count`) |
| An `.xlsx` unpacking past 50 MB, of more than 1,000 parts, too many XML elements, a row past 1,048,576 or wider than 200 cells | Crafted files, not built for the browser | `backend/tests/imports/test_parser.py` (`test_an_xlsx_that_unpacks_past_50_mb_is_refused_before_openpyxl_opens_it`, `test_a_workbook_with_too_many_parts_is_refused_before_any_is_read`, `test_the_element_budget_is_for_the_whole_file`, `test_a_row_past_excels_last_or_wider_than_200_cells_is_refused`) |
| A second upload while one is being read | Needs two uploads at once | `backend/tests/imports/test_api.py` (`test_a_second_upload_while_one_is_being_read_is_a_409`) |
| An upload or approve past 25,000 employees (D72) | Needs 10,001 new employees | `backend/tests/imports/test_staging.py` (`test_the_cap_is_25_000_and_its_message_says_so`) |
| A reset while a file is read or applied | Needs both at once | `backend/tests/demo/test_api.py` (`test_a_reset_while_a_file_is_being_read_is_409`), `backend/tests/demo/test_services.py` (`test_a_reset_while_a_file_is_being_read_or_applied_is_a_conflict`) |
| A generated sample file on an empty database | The page turns those downloads off | `backend/tests/demo/test_api.py` (`test_the_file_list_and_the_downloads`) |
| A template for an unknown country | The template menu offers known countries alone | `backend/tests/imports/test_template.py` (`test_an_unknown_country_is_a_404`) |
| An `on` before 1900, an insight period before 1 April 2020 or with From after To sent to the API | The UI never sends them | `backend/tests/core/test_dates.py` (`test_parse_on_starts_in_1900`), `backend/tests/insights/test_api.py` (`test_a_period_before_the_cut_off_is_a_400_where_the_dates_reach_back`) |
| A malformed amount, a component twice, more lines than a country has, `employee_code` or `legacy_code` sent to the API | The forms never send them | `backend/tests/compensation/test_api.py` (`test_a_malformed_amount_is_keyed_by_its_index_in_lines`, `test_a_component_listed_twice_is_a_400`, `test_a_body_with_more_lines_than_any_country_has_is_refused`), `backend/tests/compensation/test_validators.py` (`test_the_api_never_sets_either_code`) |
| Cancelling a record that is not scheduled, and a second exit | The page offers neither | `backend/tests/compensation/test_services.py` (`test_cancel_the_current_record_is_a_409`, `test_cancel_twice_is_a_409`), `backend/tests/compensation/test_validators.py` (`test_a_different_last_date_on_an_exited_employee_is_a_conflict`) |
| A refresh that is not JSON, and the refresh throttle of 30 a minute | Sent by the client alone | `backend/tests/accounts/test_api.py` (`test_the_refresh_endpoint_takes_json_only`, `test_the_refresh_endpoint_is_throttled_per_client_address`) |
| A restart after Empty the database leaving it empty (D79) | A restart was not re-run in the browser | `backend/tests/seed/test_seed.py` (`test_if_empty_leaves_a_database_emptied_on_the_demo_data_page_empty`, `test_if_empty_seeds_a_fresh_database`, `test_if_empty_seeds_again_after_a_seed_cut_short`) |
| Safari, Firefox and phones | Chrome alone was driven, and the frame is at least 1024 px wide (D75) | none |

## Local check of the icon and the credit

On a local container of `2674b94`, rebuilt by Claude Code with the owner's approval, at the three sizes the owner named. The window was 1280 by 720, then the shortest Chrome allows (1280 by 198), then 200% zoom (640 by 360).

| # | Area | Steps | Expected | Observed | Result |
| --- | --- | --- | --- | --- | --- |
| 1 | Nav | The credit at 1280 by 720 | At the nav's foot, below Help, nothing else scrolling | Help's bottom 305 px, the credit's top 687 px, 18 px from the foot, main alone scrolling (75 px) | Pass |
| 2 | Nav | The credit at the shortest window | Below Help, the nav alone scrolling | 21 px below Help, the nav scrolling 161 px, html, body, #root and the frame without a scrollbar | Pass |
| 3 | Nav | The credit at 200% | Below Help, never covering an item | 21 px below Help, the nav scrolling 6 px, no vertical scrollbar on html, body or #root, which scroll 384 px sideways below 1024 px as D75 sets | Pass |
| 4 | Nav | Tab from Help, then Enter | The focus ring and the underline, then nutanprabhat.dev in a new tab, the app where it was | A 2 px #2F4A7A ring and the underline, the new tab at https://nutanprabhat.dev/ confirmed from the tab list and closed, the app still on its page | Pass |
| 5 | Nav | Contrast | 4.5:1 or more | 7.12:1, 12 px rgb(79, 89, 101) on white | Pass |
| 6 | Login | The card and the credit at 1280 by 720, the shortest window and 200% | Both whole or reachable by scrolling, never overlapping | Centred 12 px under the card at every size: no page scroll at 1280 by 720 or at 200%, a 156 px page scroll at 198 px with the credit whole at the bottom, and a 34 px scroll at 200% once the empty fields show their errors | Pass |
| 7 | Login | Tab order, focus and Enter | Email, Password, Sign in, then the credit, which opens nutanprabhat.dev in a new tab | In that order, with the ring and the underline, the new tab confirmed and closed, Sign in never pressed | Pass |
| 8 | Login | Contrast | 4.5:1 or more | 6.50:1 on the page's background | Pass |
| 9 | Icons | /favicon.svg, /favicon.ico, /apple-touch-icon.png and the head's links, then a hard reload | 200 with an image type each, three links, no console error | 200 with image/svg+xml, image/x-icon and image/png, the three links in document.head, no console error. The extension cannot capture an SVG document, so the icon was drawn in an image at 256, 32 and 16 px and looked at there | Pass |

The owner checked by eye on the live site that the tab shows ACME's icon and that the credit sits under the login card.

## Live pass

On release v20 (`2674b94`), read-only, at 1280 by 720, on 9 October from 20:44 to 20:50 IST. Nothing was uploaded, approved, revised, exited, created or reset.

| # | Area | Steps | Expected | Observed | Result |
| --- | --- | --- | --- | --- | --- |
| 1 | Session | Open the site after the deploy | The login, every earlier session ended (D76) | The login, "Sign in · ACME Salary", the three icons linked. The owner signed in in the tab | Pass |
| 2 | Dashboard | The default view | Last 12 months, the seed's figures, no error | 10,000 on staff, USD 969M, Spent in period USD 892.7M, October 2026 rates, nine cards under three headings | Pass |
| 3 | Dashboard | Last FY | The state on 31 March 2026 | 9,155 on 31 Mar 2026 | Pass |
| 4 | Dashboard | India | India alone | 4,504, one country | Pass |
| 5 | Dashboard | Export payroll by country as CSV | One row for India with the filters | India, 4,504, USD at October 2026 rates | Pass |
| 6 | Employees | Page 2 | Ten rows from ACME-45 | As expected, 10,000 employees | Pass |
| 7 | Employees | Search harini | The matches | "7 employees match", ACME-1 first | Pass |
| 8 | Employee page | ACME-1, the Audit tab | The audit trail | The revisions with who and when | Pass |
| 9 | Imports | Open it | The drop zone and the list | "No imports yet." on the live site | Pass |
| 10 | Demo data | Open it | The seven files and the note on the base file | All seven offered, the note naming the trend, the bridge and Spent in period | Pass |
| 11 | Help | Open it | The Audit tab and the rates sentences | Both | Pass |
| 12 | Demo data | Download exits.xlsx | A sheet of 100 rows | 100 rows in the template's shape | Pass |
| 13 | Employee page | /employees/999999 | Not found | "This employee does not exist. Go back to the directory." | Pass |
| 14 | Any | /nowhere/at/all | Page not found in the frame | As expected, the nav kept | Pass |
| 15 | Nav | The credit, then Enter | nutanprabhat.dev in a new tab | https://nutanprabhat.dev/ in a new tab, confirmed from the tab list and closed, `rel="noopener noreferrer"` | Pass |
| 16 | Tab and login | The tab icon and the credit under the login card | ACME's icon, the credit under the card | Checked by the owner by eye | Pass |
| 17 | Session | Sign out | The login with its credit and its own title | "Sign in · ACME Salary", the credit under the card | Pass |

No defect was found on the live site.

## Smoke check of the close's fixes on v21

Release v21, deployed by the owner from `310adb2`, image `registry.fly.io/acme-salary:deployment-01M4H404818JX0C2DD369RK7V1` (sha256 `da15a3c2`), opening Ship (step 14). Read-only, on 10 October from 01:33 to 01:37 IST, the HR Manager signed in by the owner. Nothing was uploaded, approved, revised, exited, created or reset.

| # | Area | Steps | Expected | Observed | Result |
| --- | --- | --- | --- | --- | --- |
| 1 | Boot | The new machine's lines in `fly logs` | Migrate, the seed's check and gunicorn, cleanly | "No migrations to apply", then `seed_data --if-empty` loaded and said "employees exist, nothing to do" (`0142ab1`, `46dfd9c`), gunicorn 26.2.0 listening at 20:01:26Z and the health check passing at 20:01:27Z, after one failed check while the machine was still starting | Pass |
| 2 | Directory | Open `/employees?page=5000` | The last page, the URL replaced, no detour (`d2318ff`) | `?page=1000`, rows 9,991 to 10,000 of 10,000, the requests for pages 5000, 1 and 1000 only, no error | Pass |
| 3 | Directory and dashboard | Open each with `country=IN,US&currency=local` | A refused country on the directory's Country field (`3288916`) | Both read the link as USD and every request answered 200, so no refusal reaches the page. The dashboard shows a refusal once under its bar by design (D76), the field is the directory's | Not produced, see Not covered |
| 4 | Directory | Gross min 200000 with Gross max 100000.50, then 100000.50 with 100000.5 | The message on both fields for the first, none for the second (`035e510`, `e2d7cff`) | "Gross min is above Gross max" on both fields, both invalid, then no message | Pass |
| 5 | Directory | Export, then CSV | The file with its header (`bfb386f`, `4ed3004`) | `acme-employees-20261009-2005.csv`, 2.0 MB, 17 columns in the header and 10,000 rows. Split on commas, semicolons or tabs with quotes ignored, no cell starts a formula | Pass |
| 6 | Every page | Open each page in the app | Each tab names its page (`2919443`) | "Dashboard", "Employees", "Harini Mishra", "New employee", "Imports", "Demo data", "Help" and "Page not found", each followed by "· ACME Salary". The import review was not reached, since the live site holds no batch and nothing was uploaded | Pass |
| 7 | Session | Sign out from an employee's page | The login with its own title | `/login` with the way back, "Sign in · ACME Salary", the refresh token gone from storage | Pass |

No defect was found. The refresh refused after a password change (`97819e6`) and `make_import_file`'s CSV (`e33663a`) cannot be reached read-only through the UI and stay with their tests.
