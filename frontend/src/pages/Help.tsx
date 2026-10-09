import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Link,
  Paper,
  Typography,
} from '@mui/material';
import { useEffect } from 'react';
import { Link as RouterLink, useLocation } from 'react-router';

import { PageHeader } from '../components/layout/PageHeader';

interface Step {
  title: string;
  text: string;
}

/** How it works, in the order the work happens. */
const STEPS: Step[] = [
  {
    title: 'Import',
    text: 'Download the template on the Imports page, fill in one row per employee and upload it as a spreadsheet. Every row is checked and staged for review, and nothing in the directory changes yet.',
  },
  {
    title: 'Review',
    text: 'Each row says what it will do: create an employee, update their details, revise their pay, or nothing. A row that gives a last day records an exit. Fix an error in the sheet and upload it again, or skip the row.',
  },
  {
    title: 'Approve',
    text: "Approve applies every accepted row together, or none of them. Every change is recorded in the employee's audit trail, with who made it and when.",
  },
  {
    title: 'Maintain',
    text: 'Find someone in Employees by name, code or email, and open them with the pencil. From their page you can add a revision or schedule one for a later date, record an exit, or edit their details. Add employee creates someone new.',
  },
  {
    title: 'Understand',
    text: 'The dashboard shows a period you choose, for the countries and departments you pick, in the reporting currency you set. Its cards answer three questions: what we spend, how pay is structured, and whether pay is fair.',
  },
  {
    title: 'Share',
    text: 'The directory and every dashboard card can be exported as CSV, Excel or JSON. An export holds everything your filters match, not only the page on screen.',
  },
];

interface Question {
  /** The answer's anchor, `/help#<id>`. */
  id: string;
  question: string;
  answer: string;
}

/** The answers come from SPEC and DECISIONS. The decision behind each is named in a comment, never
 * on the page. */
const QUESTIONS: Question[] = [
  // D59, D60, D62, D68: 5 people for a total, mean or median, 20 for a spread, 5 women and 5 men
  // for a comparison, and the figures that would give a withheld one back by subtraction.
  {
    id: 'hidden-figures',
    question: 'Why does a figure say "fewer than 5 people" or "fewer than 20 people"?',
    answer:
      "A figure is hidden when it could show one person's pay. Counts always show, but totals, means and medians need at least 5 people, and spreads such as percentiles and the salary distribution need at least 20. A comparison of women and men needs at least 5 of each. A figure that adds up with others, such as a share or a part of the cost bridge, can be hidden too, because subtracting it from the rest would give a hidden figure back.",
  },
  // D13, D59, D64: USD by default, EUR, or local for one country, at the rate in force on `to`.
  {
    id: 'currency',
    question: "Which currency are the figures in, and at which month's rate?",
    answer:
      "Figures are in US dollars unless you choose euros, or Local when exactly one country is selected. Pay is stored in each country's own currency and converted when you look, at the month's rate in force on the last day of the period, which the dashboard names, such as October 2026 rates. One rate converts the whole period, so a change over time is never a change in exchange rates. The directory and the employee pages convert at today's rate.",
  },
  // D62, D69, D70: who left on or after 1 April 2020, and the three movement figures it skips.
  {
    id: 'include-exited',
    question: 'What does Include exited do, and where does it not apply?',
    answer:
      "Include exited adds the people who left on or after 1 April 2020 and before the period's last day, counted at their last pay. The cost trend, the cost bridge and Spent in period always count the people employed on each date, so it does not change them, and each says so while it is ticked.",
  },
  // D70: the reporting cut-off, the start of FY 2020-21.
  {
    id: 'reporting-start',
    question: 'Why do the dates start on 1 April 2020?',
    answer:
      "Reporting starts on 1 April 2020, the first day of ACME's financial year 2020-21, so no period can start earlier. Every pay record is kept, so any period from then to today is exact. A record that began before 1 April 2020 counts for the days it covers inside the period.",
  },
  // SPEC F3 and section 4 rule 3, D43: cancelled, not deleted, and the date is free again.
  {
    id: 'scheduled-revision',
    question: 'What is a scheduled revision, and how do I cancel one?',
    answer:
      "A scheduled revision is a pay change dated after today. Today's pay stays current until that date, and the revision shows in the employee's history as scheduled. To cancel it before it takes effect, open the employee and choose Cancel on its row. The row stays in the history, marked cancelled, and its date can be used again.",
  },
  // SPEC section 4 rule 6, D72: the reset is the one operation that deletes.
  {
    id: 'no-deletion',
    question: 'Why can nothing be deleted?',
    answer:
      'Pay records are never deleted, so every figure can be traced back to what was entered. Someone who leaves is recorded as exited, a change of pay is a new revision, and a scheduled revision is cancelled, not removed. The one exception is Empty the database on the Demo data page, which clears the demo data behind your password so a reviewer can start again.',
  },
  // SPEC F2, D24, D57, D72: error rows, rows that changed since upload, and the 25,000 cap.
  {
    id: 'approve-refused',
    question: 'Why is Approve refused, and how do I fix it?',
    answer:
      "Approve stays off while any row has an error. Skip those rows, or fix them in the sheet and upload it again. Approve is also refused when a row would now do something other than what you reviewed, because the employee changed after the upload or another batch took a new employee's legacy code: those rows are marked as errors, to skip or upload again. It is refused too when the batch's new employees would take ACME past 25,000 employees.",
  },
  // D72: the warning on a revision that lowers gross.
  {
    id: 'gross-decrease',
    question: 'What does the warning "gross falls from" mean?',
    answer:
      'It means a revision would pay someone less than the record it replaces, and it names both figures, for example gross falls from 1,450,000.00 to 1,380,000.00 INR. It is a warning, not an error, so the row can still be approved. It often points to an old file or a typing mistake, so check the row before you approve.',
  },
  // SPEC F1, D72: matched by legacy code, and a repeated scheduled revision is a no-op too.
  {
    id: 'same-file-twice',
    question: 'What happens if I import the same file twice?',
    answer:
      'Nothing changes the second time. Rows are matched to employees by their legacy code, so a row that repeats what is already on file, a scheduled revision included, is counted as No-op and left out when you approve.',
  },
  // D72 and SPEC section 13's long requests: the busy dialog and the polling after a cut.
  {
    id: 'long-imports',
    question: 'Why can a large import or approve take a few minutes?',
    answer:
      'The demo runs on a small shared machine, and reading or applying thousands of rows is heavy work for it. While it works, a dialog shows the seconds passing and the page cannot be changed, so nothing starts twice. If the connection drops, the server carries on and the page keeps checking until the batch is ready.',
  },
  // D48: the ACME code is the app's, the legacy code the sheet's.
  {
    id: 'codes',
    question: 'What is the difference between the ACME code and the legacy code?',
    answer:
      'The ACME code, such as ACME-17, is given by the app to every employee and never changes. The legacy code is the one the previous HR system used, kept exactly as the sheet had it, and imports use it to find the right person. Someone added in the app has no legacy code, so no spreadsheet can change them. Search finds people by either code.',
  },
  // SPEC F8, D21: 12 hours from sign-in however often the page refreshes, and logout ends it.
  {
    id: 'session',
    question: 'How long does a session last?',
    answer:
      'You stay signed in for up to 12 hours from when you sign in, however active you are. The page renews its access in the background, and when the 12 hours are up it asks you to sign in again. Sign out ends the session in this browser at once, and it cannot be renewed.',
  },
];

/** Help (D75): how the app works, and the questions it raises, answered. Static: no API call. */
export function Help() {
  const { hash } = useLocation();
  // Every anchor is a plain slug, so the hash is read as it stands: decoding it would throw on a
  // stray % in a link.
  const target = hash.slice(1);

  // A link to an answer opens it (defaultExpanded below), brings it into view and gives its
  // question the focus, so the keyboard goes on from there. This runs after the shell has put main
  // back at the top and focused it.
  useEffect(() => {
    if (!target) return;
    document.getElementById(target)?.scrollIntoView({ block: 'start' });
    document.getElementById(`${target}-question`)?.focus({ preventScroll: true });
  }, [target]);

  return (
    <Box sx={{ maxWidth: '72ch' }}>
      <PageHeader
        title="Help"
        subtitle="How the app works, and answers to the questions it raises."
      />

      <Box component="section" aria-labelledby="how-it-works" sx={{ mb: 8 }}>
        <Typography id="how-it-works" variant="h2" sx={{ mb: 3 }}>
          How it works
        </Typography>
        {/* Safari drops a list's role once its markers are off, so the role is said outright. */}
        <Paper component="ol" role="list" sx={{ m: 0, p: 0, listStyle: 'none' }}>
          {STEPS.map((step, index) => (
            <Box
              component="li"
              key={step.title}
              sx={{
                display: 'grid',
                gridTemplateColumns: '40px minmax(0, 1fr)',
                columnGap: 3,
                px: 5,
                py: 4,
                '& + &': { borderTop: 1, borderColor: 'divider' },
              }}
            >
              {/* The list already says which step this is, so the figure is for the eye alone. */}
              <Typography
                aria-hidden
                className="num"
                sx={{ fontSize: 20, lineHeight: '24px', fontWeight: 600, color: 'primary.main' }}
              >
                {index + 1}
              </Typography>
              <Box>
                <Typography component="h3" variant="h3">
                  {step.title}
                </Typography>
                <Typography sx={{ mt: 1 }}>{step.text}</Typography>
              </Box>
            </Box>
          ))}
        </Paper>
        <Typography sx={{ mt: 4 }}>
          To try all of this safely, the{' '}
          <Link component={RouterLink} to="/demo">
            Demo data page
          </Link>{' '}
          has sample files to import and can empty the database so you can start again.
        </Typography>
      </Box>

      <Box component="section" aria-labelledby="questions">
        <Typography id="questions" variant="h2" sx={{ mb: 3 }}>
          Questions
        </Typography>
        {/* Keyed on the anchor, so a link to another answer while this page is open opens it. */}
        <Paper key={target}>
          {QUESTIONS.map((item) => (
            <Accordion
              key={item.id}
              id={item.id}
              defaultExpanded={item.id === target}
              disableGutters
              square
              // No motion (D75): the answer opens at once.
              slotProps={{ transition: { timeout: 0 } }}
              sx={{
                border: 0,
                scrollMarginTop: 24,
                '&::before': { display: 'none' },
                '& + &': { borderTop: 1, borderColor: 'divider' },
              }}
            >
              <AccordionSummary
                expandIcon={<ExpandMoreIcon />}
                id={`${item.id}-question`}
                aria-controls={`${item.id}-answer`}
                sx={{ px: 5, '& .MuiAccordionSummary-expandIconWrapper': { transition: 'none' } }}
              >
                <Typography component="span" sx={{ fontWeight: 600 }}>
                  {item.question}
                </Typography>
              </AccordionSummary>
              {/* The accordion gives this region the summary's aria-controls as its id. */}
              <AccordionDetails sx={{ px: 5, pt: 0, pb: 4 }}>
                <Typography>{item.answer}</Typography>
              </AccordionDetails>
            </Accordion>
          ))}
        </Paper>
      </Box>
    </Box>
  );
}
