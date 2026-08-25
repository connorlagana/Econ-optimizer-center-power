export const pct = (x: number, digits = 2) =>
  `${x >= 0 ? '+' : '−'}${Math.abs(x).toFixed(digits)}%`;

export const pctPlain = (x: number, digits = 1) => `${(x * 100).toFixed(digits)}%`;

export const usdM = (x: number, digits = 1) => `$${(x / 1e6).toFixed(digits)}M`;

export const mw = (x: number, digits = 1) => `${x.toFixed(digits)} MW`;

export const mwh = (x: number) => `${Math.round(x).toLocaleString('en-US')} MWh`;

export const usd = (x: number, digits = 4) => `$${x.toFixed(digits)}`;

/**
 * Landmine 10: the LP's answer is a continuous optimum and is not buildable.
 * Interconnection comes in transformer sizes, generators in unit sizes. Never
 * show a spec without showing the rounding next to it.
 */
export function procurable(valueMw: number, stepMw: number): number {
  return Math.ceil(valueMw / stepMw) * stepMw;
}
