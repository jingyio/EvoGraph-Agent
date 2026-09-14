export const legacyPages = [
  "experiments",
  "trajectory",
  "compare",
  "insights",
  "replay",
  "showcase",
  "live",
  "demo",
  "evaluation",
  "evolution",
  "taskbank",
  "platforms",
] as const;
export function canonicalHash(hash: string): string {
  const [page, query = ""] = hash.replace(/^#/, "").split("?");
  if (page === "employees" || !page) return "#home";
  if (page === "evidence") return `#analysis${query ? "?" + query : ""}`;
  if (page === "home" || page === "analysis" || page === "archive") return hash;
  if ((legacyPages as readonly string[]).includes(page))
    return `#archive?page=${page}${query ? "&" + query : ""}`;
  return "#home";
}
export function archiveExperiment(): string {
  return (
    new URLSearchParams(window.location.hash.split("?")[1] || "").get(
      "experiment",
    ) || ""
  );
}
