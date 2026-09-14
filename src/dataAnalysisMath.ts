export type PairedMeasures = {
  baseline: { tokens?: number | null; durationMs?: number | null };
  rsi: { tokens?: number | null; durationMs?: number | null };
};

export type CumulativeMeasures = {
  order: number;
  baselineCumulativeTokens: number | null;
  rsiCumulativeTokens: number | null;
  baselineCumulativeLatency: number | null;
  rsiCumulativeLatency: number | null;
  tokenSavingRate: number | null;
  latencySavingRate: number | null;
};

export function cumulativePoints<T extends PairedMeasures>(points: T[]): Array<T & CumulativeMeasures> {
  let baselineTokens = 0;
  let rsiTokens = 0;
  let baselineLatency = 0;
  let rsiLatency = 0;
  let tokensKnown = true;
  let latencyKnown = true;
  return points.map((point, index) => {
    if (point.baseline.tokens == null || point.rsi.tokens == null) tokensKnown = false;
    if (point.baseline.durationMs == null || point.rsi.durationMs == null) latencyKnown = false;
    if (tokensKnown) {
      baselineTokens += point.baseline.tokens!;
      rsiTokens += point.rsi.tokens!;
    }
    if (latencyKnown) {
      baselineLatency += point.baseline.durationMs!;
      rsiLatency += point.rsi.durationMs!;
    }
    const baselineCumulativeTokens = tokensKnown ? baselineTokens : null;
    const rsiCumulativeTokens = tokensKnown ? rsiTokens : null;
    const baselineCumulativeLatency = latencyKnown ? baselineLatency : null;
    const rsiCumulativeLatency = latencyKnown ? rsiLatency : null;
    return {
      ...point,
      order: index + 1,
      baselineCumulativeTokens,
      rsiCumulativeTokens,
      baselineCumulativeLatency,
      rsiCumulativeLatency,
      tokenSavingRate:
        baselineCumulativeTokens && rsiCumulativeTokens != null
          ? (baselineCumulativeTokens - rsiCumulativeTokens) / baselineCumulativeTokens
          : null,
      latencySavingRate:
        baselineCumulativeLatency && rsiCumulativeLatency != null
          ? (baselineCumulativeLatency - rsiCumulativeLatency) / baselineCumulativeLatency
          : null,
    };
  });
}
