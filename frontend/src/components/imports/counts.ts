/** A count as the batch pages write it: `1,250`. */
export function formatCount(count: number) {
  return count.toLocaleString('en-US');
}

/** What an approve did, each count written as the strip writes it: `1,250 created, ...`. */
export function appliedCounts(batch: {
  created_rows: number;
  updated_rows: number;
  revised_rows: number;
}) {
  return (
    `${formatCount(batch.created_rows)} created, ${formatCount(batch.updated_rows)} updated, ` +
    `${formatCount(batch.revised_rows)} revised.`
  );
}

export function rowsWord(count: number) {
  return `${formatCount(count)} ${count === 1 ? 'row' : 'rows'}`;
}
