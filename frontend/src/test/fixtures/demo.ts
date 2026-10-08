import type { ResetCounts, SampleFiles } from '../../api/types';

// The Demo data page's payloads (SPEC F9, D72), as the API shapes them.

export const sampleFiles: SampleFiles = {
  employees: 27,
  files: [
    {
      name: 'base',
      file_name: 'base-15000.xlsx',
      description:
        'The whole organisation, 10,000 on staff and 5,000 who left, as the seed built it. Into an empty database it creates everyone; into the seeded one every row is a no-op, the scale test.',
      available: true,
    },
    {
      name: 'newhires',
      file_name: 'newhires.xlsx',
      description:
        '500 new employees with fresh legacy codes who joined between 60 days ago and 14 days ahead, the future ones shown as Upcoming until they join. Each row creates an employee.',
      available: true,
    },
    {
      name: 'diwali-bonus',
      file_name: 'diwali-bonus.xlsx',
      description:
        '1,000 employees with 5 to 15% of base added to their bonus, effective today. Each row is a revision.',
      available: true,
    },
    {
      name: 'april-raises',
      file_name: 'april-raises.xlsx',
      description:
        '1,000 employees with base up 3 to 8%, components with it, effective 1 April next. Each row is a scheduled revision.',
      available: true,
    },
    {
      name: 'promotions',
      file_name: 'promotions.xlsx',
      description:
        '200 employees one level up with the designation to match and base up 12 to 20%, effective today. Each row changes identity and amounts at once.',
      available: true,
    },
    {
      name: 'exits',
      file_name: 'exits.xlsx',
      description:
        '100 employees with their last day between 14 days ago and 60 days ahead: the past ones leave the counts at once, the future ones are scheduled exits and stay active until the day. Each row is an exit.',
      available: true,
    },
    {
      name: 'fix-me',
      file_name: 'fix-me.xlsx',
      description:
        '50 rows, 30 raises and 20 new joiners, with 6 planted errors to skip or fix in the sheet.',
      available: true,
    },
  ],
};

/** An empty database: only the committed base file can be downloaded. */
export const sampleFilesEmpty: SampleFiles = {
  employees: 0,
  files: sampleFiles.files.map((file) => ({ ...file, available: file.name === 'base' })),
};

export const resetCounts: ResetCounts = {
  employees: 15000,
  compensation_records: 51659,
  compensation_lines: 128000,
  import_batches: 3,
  import_rows: 150,
  audit_entries: 70000,
};
