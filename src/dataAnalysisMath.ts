export type PairedMeasures = {
  baseline: {
    tokens?: number | null;
    costUsd?: number | null;
    durationMs?: number | null;
    modelRequests?: number | null;
    passed?: boolean;
  };
  rsi: {
    tokens?: number | null;
    costUsd?: number | null;
    durationMs?: number | null;
    modelRequests?: number | null;
    passed?: boolean;
  };
};


export type ScopeQualityPoint = {
  baseline: { passed?: boolean; usageComplete?: boolean };
  rsi: { passed?: boolean; usageComplete?: boolean };
};

export function scopeAllowsCostClaims(
  points: ScopeQualityPoint[],
  releaseAllowed: boolean,
  cohortAllowed = false,
): boolean {
  return (
    points.length > 0 &&
    points.every(
      (point) =>
        point.baseline.passed === true &&
        point.rsi.passed === true &&
        point.baseline.usageComplete === true &&
        point.rsi.usageComplete === true,
    ) &&
    (releaseAllowed || cohortAllowed)
  );
}

export type CumulativeMeasures = {
  order: number;
  baselineCumulativeTokens: number | null;
  rsiCumulativeTokens: number | null;
  baselineCumulativeCostUsd: number | null;
  rsiCumulativeCostUsd: number | null;
  baselineCumulativeLatency: number | null;
  rsiCumulativeLatency: number | null;
  baselineCumulativeRequests: number | null;
  rsiCumulativeRequests: number | null;
  baselineCumulativeAccuracy: number | null;
  rsiCumulativeAccuracy: number | null;
  tokenSavingRate: number | null;
  costSavingRate: number | null;
  latencySavingRate: number | null;
  requestSavingRate: number | null;
};

export type RevisionEvidence = {
  sourcePairId?: string;
  sourceTaskId?: string;
  sourceRunId?: string;
  versionId?: string;
  parentVersionId?: string;
  graphChanged?: boolean;
  matchingChanged?: boolean;
  graphDiff?: unknown[];
  matchingDiff?: unknown[];
  subsequentUses?: Array<{ pairId?: string; taskId?: string; runId?: string }>;
};

export type LearningEvidencePoint = {
  pairId?: string;
  workpackId: string;
  generatedVersionIds?: string[];
  generatedMatchVersions?: Array<string | number>;
  usedVersionId?: string | null;
  usedMatchVersion?: string | number | null;
};

export function scopedRevisionEvidence(
  revisions: RevisionEvidence[],
  points: LearningEvidencePoint[],
): RevisionEvidence[] {
  const ids = new Set(
    points.flatMap((point) => [point.pairId, point.workpackId]).filter(Boolean),
  );
  return revisions
    .filter(
      (revision) =>
        ids.has(revision.sourcePairId) || ids.has(revision.sourceTaskId),
    )
    .map((revision) => ({
      ...revision,
      subsequentUses: (revision.subsequentUses || []).filter(
        (use) => ids.has(use.pairId) || ids.has(use.taskId),
      ),
    }));
}

export type RevisionVisualState = {
  graphRevision: boolean;
  matchingRevision: boolean;
  verifiedLaterUse: boolean;
  usesGraphRevision: boolean;
  usesMatchingRevision: boolean;
};

function hasMaterialDiff(value: unknown): boolean {
  if (Array.isArray(value)) return value.length > 0;
  if (value && typeof value === "object") return Object.keys(value).length > 0;
  return false;
}

export function revisionIsAuditable(
  revision: RevisionEvidence,
  kind: "graph" | "matching",
): boolean {
  return (
    Boolean(revision.sourceRunId) &&
    revision[`${kind}Changed`] === true &&
    hasMaterialDiff(revision[`${kind}Diff`])
  );
}

export function revisionVisualState(
  point: LearningEvidencePoint,
  revisions: RevisionEvidence[],
): RevisionVisualState {
  const ids = new Set([point.pairId, point.workpackId].filter(Boolean));
  const sourced = revisions.filter(
    (revision) =>
      ids.has(revision.sourcePairId) || ids.has(revision.sourceTaskId),
  );
  const used = revisions.filter((revision) =>
    (revision.subsequentUses || []).some(
      (use) =>
        Boolean(use.runId) &&
        (ids.has(use.pairId) || ids.has(use.taskId)),
    ),
  );
  const graphRevision = sourced.some((revision) =>
    revisionIsAuditable(revision, "graph"),
  );
  const matchingRevision = sourced.some((revision) =>
    revisionIsAuditable(revision, "matching"),
  );
  return {
    graphRevision,
    matchingRevision,
    verifiedLaterUse: sourced.some(
      (revision) =>
        (revisionIsAuditable(revision, "graph") ||
          revisionIsAuditable(revision, "matching")) &&
        Boolean(revision.subsequentUses?.some((use) => use.runId)),
    ),
    usesGraphRevision: used.some((revision) =>
      revisionIsAuditable(revision, "graph"),
    ),
    usesMatchingRevision: used.some((revision) =>
      revisionIsAuditable(revision, "matching"),
    ),
  };
}

export type EvolutionSignals = {
  createdGraph: boolean;
  createdMatching: boolean;
  graphRevision: boolean;
  matchingRevision: boolean;
  usedGraph: boolean;
  usedMatching: boolean;
  usedGraphRevision: boolean;
  usedMatchingRevision: boolean;
};

export function evolutionSignals(
  point: LearningEvidencePoint,
  revisions: RevisionEvidence[],
): EvolutionSignals {
  const ids = new Set([point.pairId, point.workpackId].filter(Boolean));
  const sourced = revisions.filter(
    (revision) =>
      ids.has(revision.sourcePairId) || ids.has(revision.sourceTaskId),
  );
  const used = revisions.filter((revision) =>
    (revision.subsequentUses || []).some(
      (use) =>
        Boolean(use.runId) &&
        (ids.has(use.pairId) || ids.has(use.taskId)),
    ),
  );
  return {
    createdGraph: Boolean(point.generatedVersionIds?.length),
    createdMatching: Boolean(point.generatedMatchVersions?.length),
    graphRevision: sourced.some((revision) => revision.graphChanged === true),
    matchingRevision: sourced.some(
      (revision) => revision.matchingChanged === true,
    ),
    usedGraph: Boolean(point.usedVersionId),
    usedMatching: point.usedMatchVersion != null,
    usedGraphRevision: used.some((revision) => revision.graphChanged === true),
    usedMatchingRevision: used.some(
      (revision) => revision.matchingChanged === true,
    ),
  };
}

export function replayPrefix<T>(points: T[], count: number | null): T[] {
  if (count == null) return points;
  const bounded = Math.max(0, Math.min(Math.floor(count), points.length));
  return points.slice(0, bounded);
}

export function firstMemoryReuseIndex<T extends LearningEvidencePoint & { index: number }>(
  points: T[],
): number | null {
  const sourcePosition = points.findIndex(
    (point) =>
      Boolean(point.generatedVersionIds?.length) ||
      Boolean(point.generatedMatchVersions?.length),
  );
  if (sourcePosition < 0) return null;
  const source = points[sourcePosition];
  const graphVersions = new Set(source.generatedVersionIds || []);
  const matchingVersions = new Set(
    (source.generatedMatchVersions || []).map((version) => String(version)),
  );
  const reused = points.slice(sourcePosition + 1).find(
    (point) =>
      (Boolean(point.usedVersionId) && graphVersions.has(point.usedVersionId!)) ||
      (point.usedMatchVersion != null &&
        matchingVersions.has(String(point.usedMatchVersion))),
  );
  return reused?.index ?? null;
}

export function cumulativePoints<T extends PairedMeasures>(
  points: T[],
): Array<T & CumulativeMeasures> {
  let baselineTokens = 0;
  let rsiTokens = 0;
  let baselineLatency = 0;
  let rsiLatency = 0;
  let baselineCostUsd = 0;
  let rsiCostUsd = 0;
  let baselineRequests = 0;
  let rsiRequests = 0;
  let baselinePassed = 0;
  let rsiPassed = 0;
  let baselineTokensKnown = true;
  let rsiTokensKnown = true;
  let baselineLatencyKnown = true;
  let rsiLatencyKnown = true;
  let baselineCostKnown = true;
  let rsiCostKnown = true;
  let baselineRequestsKnown = true;
  let rsiRequestsKnown = true;
  let baselineAccuracyKnown = true;
  let rsiAccuracyKnown = true;
  return points.map((point, index) => {
    if (point.baseline.tokens == null) baselineTokensKnown = false;
    if (point.rsi.tokens == null) rsiTokensKnown = false;
    if (point.baseline.durationMs == null) baselineLatencyKnown = false;
    if (point.rsi.durationMs == null) rsiLatencyKnown = false;
    if (point.baseline.costUsd == null) baselineCostKnown = false;
    if (point.rsi.costUsd == null) rsiCostKnown = false;
    if (point.baseline.modelRequests == null) baselineRequestsKnown = false;
    if (point.rsi.modelRequests == null) rsiRequestsKnown = false;
    if (typeof point.baseline.passed !== "boolean")
      baselineAccuracyKnown = false;
    if (typeof point.rsi.passed !== "boolean") rsiAccuracyKnown = false;
    if (baselineTokensKnown) baselineTokens += point.baseline.tokens!;
    if (rsiTokensKnown) rsiTokens += point.rsi.tokens!;
    if (baselineLatencyKnown) baselineLatency += point.baseline.durationMs!;
    if (rsiLatencyKnown) rsiLatency += point.rsi.durationMs!;
    if (baselineCostKnown) baselineCostUsd += point.baseline.costUsd!;
    if (rsiCostKnown) rsiCostUsd += point.rsi.costUsd!;
    if (baselineRequestsKnown)
      baselineRequests += point.baseline.modelRequests!;
    if (rsiRequestsKnown) rsiRequests += point.rsi.modelRequests!;
    if (baselineAccuracyKnown) baselinePassed += point.baseline.passed ? 1 : 0;
    if (rsiAccuracyKnown) rsiPassed += point.rsi.passed ? 1 : 0;
    const baselineCumulativeTokens = baselineTokensKnown
      ? baselineTokens
      : null;
    const rsiCumulativeTokens = rsiTokensKnown ? rsiTokens : null;
    const baselineCumulativeLatency = baselineLatencyKnown
      ? baselineLatency
      : null;
    const rsiCumulativeLatency = rsiLatencyKnown ? rsiLatency : null;
    const baselineCumulativeCostUsd = baselineCostKnown
      ? baselineCostUsd
      : null;
    const rsiCumulativeCostUsd = rsiCostKnown ? rsiCostUsd : null;
    const baselineCumulativeRequests = baselineRequestsKnown
      ? baselineRequests
      : null;
    const rsiCumulativeRequests = rsiRequestsKnown ? rsiRequests : null;
    const baselineCumulativeAccuracy = baselineAccuracyKnown
      ? baselinePassed / (index + 1)
      : null;
    const rsiCumulativeAccuracy = rsiAccuracyKnown
      ? rsiPassed / (index + 1)
      : null;
    return {
      ...point,
      order: index + 1,
      baselineCumulativeTokens,
      rsiCumulativeTokens,
      baselineCumulativeLatency,
      rsiCumulativeLatency,
      baselineCumulativeCostUsd,
      rsiCumulativeCostUsd,
      baselineCumulativeRequests,
      rsiCumulativeRequests,
      baselineCumulativeAccuracy,
      rsiCumulativeAccuracy,
      tokenSavingRate:
        baselineCumulativeTokens && rsiCumulativeTokens != null
          ? (baselineCumulativeTokens - rsiCumulativeTokens) /
            baselineCumulativeTokens
          : null,
      costSavingRate:
        baselineCumulativeCostUsd && rsiCumulativeCostUsd != null
          ? (baselineCumulativeCostUsd - rsiCumulativeCostUsd) /
            baselineCumulativeCostUsd
          : null,
      latencySavingRate:
        baselineCumulativeLatency && rsiCumulativeLatency != null
          ? (baselineCumulativeLatency - rsiCumulativeLatency) /
            baselineCumulativeLatency
          : null,
      requestSavingRate:
        baselineCumulativeRequests && rsiCumulativeRequests != null
          ? (baselineCumulativeRequests - rsiCumulativeRequests) /
            baselineCumulativeRequests
          : null,
    };
  });
}

const rawRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" ? (value as Record<string, unknown>) : {};
const rawString = (value: unknown): string | undefined =>
  typeof value === "string" && value ? value : undefined;
const rawStrings = (value: unknown): string[] =>
  Array.isArray(value)
    ? value.filter(
        (item): item is string => typeof item === "string" && Boolean(item),
      )
    : [];

export function normalizedRevisionEvidence(
  explicit: unknown,
  rawPairs: unknown,
): RevisionEvidence[] {
  if (Array.isArray(explicit)) return explicit as RevisionEvidence[];
  const pairs = Array.isArray(rawPairs) ? rawPairs.map(rawRecord) : [];
  return pairs.flatMap((pair, sourceIndex) => {
    const spec = rawRecord(pair.spec);
    const experience = rawRecord(pair.experienceAfter);
    const versions = Array.isArray(experience.onlineRsiVersions)
      ? experience.onlineRsiVersions.map(rawRecord)
      : [];
    return versions.flatMap((version) => {
      const generation =
        typeof version.generation === "number" ? version.generation : 0;
      const matchVersion =
        typeof version.matchVersion === "number" ? version.matchVersion : 0;
      const patches = Array.isArray(version.patches)
        ? version.patches.map(rawRecord)
        : [];
      const matchPatches = Array.isArray(version.matchPatches)
        ? version.matchPatches.map(rawRecord)
        : [];
      const graphChanged =
        Boolean(version.parentGraphId || generation > 0) &&
        patches.some(
          (patch) =>
            JSON.stringify(patch.before) !== JSON.stringify(patch.after),
        );
      const matchingChanged =
        matchVersion > 0 &&
        matchPatches.some(
          (patch) =>
            patch.before != null &&
            JSON.stringify(patch.before) !== JSON.stringify(patch.after),
        );
      if (!graphChanged && !matchingChanged) return [];
      const versionId = rawString(version.id);
      const subsequentUses = versionId
        ? pairs.slice(sourceIndex + 1).flatMap((later) => {
            const laterSpec = rawRecord(later.spec);
            const run = rawRecord(later.online_rsi || later.onlineRsi);
            const evolution = rawRecord(run.evolution);
            const used = [
              rawString(evolution.usedVersionId),
              ...rawStrings(evolution.usedVersionIds),
            ];
            const graphExecuted =
              Array.isArray(run.toolTrace) &&
              run.toolTrace
                .map(rawRecord)
                .some(
                  (trace) => trace.executor === "graph" && trace.ok === true,
                );
            return used.includes(versionId) && graphExecuted
              ? [
                  {
                    pairId: rawString(laterSpec.id),
                    taskId: rawString(laterSpec.id),
                    runId: rawString(run.id),
                  },
                ]
              : [];
          })
        : [];
      return [
        {
          sourcePairId: rawString(spec.id),
          sourceTaskId: rawString(spec.id),
          sourceRunId: rawString(version.sourceRunId),
          versionId,
          parentVersionId: rawString(version.parentGraphId),
          graphChanged,
          matchingChanged,
          graphDiff: patches,
          matchingDiff: matchPatches,
          subsequentUses,
        } satisfies RevisionEvidence,
      ];
    });
  });
}

export function releaseAllowsCostClaims(
  status: string | undefined,
  backendAllows: boolean | undefined,
): boolean {
  return (status === "formal" || status === "historical") && backendAllows !== false;
}

export function attributionTimelineHeading(taskCount: number): string {
  return `${taskCount || 0}任务机会链与实际证据`;
}
