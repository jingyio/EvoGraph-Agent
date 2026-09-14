export type PairedMeasures = {
  baseline: { tokens?: number | null; durationMs?: number | null; modelRequests?: number | null; passed?: boolean };
  rsi: { tokens?: number | null; durationMs?: number | null; modelRequests?: number | null; passed?: boolean };
};

export type CumulativeMeasures = {
  order: number;
  baselineCumulativeTokens: number | null;
  rsiCumulativeTokens: number | null;
  baselineCumulativeLatency: number | null;
  rsiCumulativeLatency: number | null;
  baselineCumulativeRequests: number | null;
  rsiCumulativeRequests: number | null;
  baselineCumulativeAccuracy: number | null;
  rsiCumulativeAccuracy: number | null;
  tokenSavingRate: number | null;
  latencySavingRate: number | null;
  requestSavingRate: number | null;
};

export function cumulativePoints<T extends PairedMeasures>(points: T[]): Array<T & CumulativeMeasures> {
  let baselineTokens = 0;
  let rsiTokens = 0;
  let baselineLatency = 0;
  let rsiLatency = 0;
  let baselineRequests = 0;
  let rsiRequests = 0;
  let baselinePassed = 0;
  let rsiPassed = 0;
  let baselineTokensKnown = true;
  let rsiTokensKnown = true;
  let baselineLatencyKnown = true;
  let rsiLatencyKnown = true;
  let baselineRequestsKnown = true;
  let rsiRequestsKnown = true;
  let baselineAccuracyKnown = true;
  let rsiAccuracyKnown = true;
  return points.map((point, index) => {
    if (point.baseline.tokens == null) baselineTokensKnown = false;
    if (point.rsi.tokens == null) rsiTokensKnown = false;
    if (point.baseline.durationMs == null) baselineLatencyKnown = false;
    if (point.rsi.durationMs == null) rsiLatencyKnown = false;
    if (point.baseline.modelRequests == null) baselineRequestsKnown = false;
    if (point.rsi.modelRequests == null) rsiRequestsKnown = false;
    if (typeof point.baseline.passed !== "boolean") baselineAccuracyKnown = false;
    if (typeof point.rsi.passed !== "boolean") rsiAccuracyKnown = false;
    if (baselineTokensKnown) baselineTokens += point.baseline.tokens!;
    if (rsiTokensKnown) rsiTokens += point.rsi.tokens!;
    if (baselineLatencyKnown) baselineLatency += point.baseline.durationMs!;
    if (rsiLatencyKnown) rsiLatency += point.rsi.durationMs!;
    if (baselineRequestsKnown) baselineRequests += point.baseline.modelRequests!;
    if (rsiRequestsKnown) rsiRequests += point.rsi.modelRequests!;
    if (baselineAccuracyKnown) baselinePassed += point.baseline.passed ? 1 : 0;
    if (rsiAccuracyKnown) rsiPassed += point.rsi.passed ? 1 : 0;
    const baselineCumulativeTokens = baselineTokensKnown ? baselineTokens : null;
    const rsiCumulativeTokens = rsiTokensKnown ? rsiTokens : null;
    const baselineCumulativeLatency = baselineLatencyKnown ? baselineLatency : null;
    const rsiCumulativeLatency = rsiLatencyKnown ? rsiLatency : null;
    const baselineCumulativeRequests = baselineRequestsKnown ? baselineRequests : null;
    const rsiCumulativeRequests = rsiRequestsKnown ? rsiRequests : null;
    const baselineCumulativeAccuracy = baselineAccuracyKnown ? baselinePassed / (index + 1) : null;
    const rsiCumulativeAccuracy = rsiAccuracyKnown ? rsiPassed / (index + 1) : null;
    return {
      ...point,
      order: index + 1,
      baselineCumulativeTokens,
      rsiCumulativeTokens,
      baselineCumulativeLatency,
      rsiCumulativeLatency,
      baselineCumulativeRequests,
      rsiCumulativeRequests,
      baselineCumulativeAccuracy,
      rsiCumulativeAccuracy,
      tokenSavingRate:
        baselineCumulativeTokens && rsiCumulativeTokens != null
          ? (baselineCumulativeTokens - rsiCumulativeTokens) / baselineCumulativeTokens
          : null,
      latencySavingRate:
        baselineCumulativeLatency && rsiCumulativeLatency != null
          ? (baselineCumulativeLatency - rsiCumulativeLatency) / baselineCumulativeLatency
          : null,
      requestSavingRate:
        baselineCumulativeRequests && rsiCumulativeRequests != null
          ? (baselineCumulativeRequests - rsiCumulativeRequests) / baselineCumulativeRequests
          : null,
    };
  });
}
