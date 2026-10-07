/** A count as the batch pages write it: `1,250`. */
export function formatCount(count: number) {
  return count.toLocaleString('en-US');
}

export function rowsWord(count: number) {
  return `${formatCount(count)} ${count === 1 ? 'row' : 'rows'}`;
}
