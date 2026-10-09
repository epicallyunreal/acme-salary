/** Read by screen readers, not shown: a header a column needs, or the block around a chart's
 * table. Put it on a block or an inline element, never on a table, which neither shrinks to 1 px
 * nor clips what it holds (D75). */
export const visuallyHidden = {
  position: 'absolute',
  width: '1px',
  height: '1px',
  margin: '-1px',
  padding: 0,
  border: 0,
  overflow: 'hidden',
  clip: 'rect(0 0 0 0)',
  whiteSpace: 'nowrap',
} as const;
