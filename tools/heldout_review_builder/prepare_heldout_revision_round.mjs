import fs from "node:fs/promises";
import path from "node:path";

const projectRoot = process.env.PROJECT_ROOT || "D:/Projects/financial knowledge graph";
const round1Path = process.env.ROUND1_PACK || path.join(projectRoot, "data/eval/adaptive_text_first_heldout_reviewed_round1_2026-07-15.json");
const outputPath = process.env.REVISION_PACK_OUTPUT || path.join(projectRoot, "data/eval/adaptive_text_first_heldout_revision_round_2026-07-15.json");

const revisions = {
  "gapfill:CD002": {
    query: "After an API synthesis change may introduce a mutagenic impurity, what does ICH M7 require for assessing the impact of the change and developing an appropriate control strategy?",
    gold: ["ich_m7_r2_C0015_774336b0", "ich_m7_r2_C0013_88f547a4"],
    reason: "Removed the unrelated ICH Q3D elemental-impurity evidence and narrowed the question to ICH M7 change assessment and control strategy.",
  },
  "gapfill:SC010": {
    query: "When quality or manufacturing problems threaten medicine availability, which ICH Q9 principles should guide patient protection, proactive risk control, and proportionate shortage mitigation?",
    gold: ["ich_q9_C0007_6a76fd84", "ich_q9_C0012_cef84513", "ich_q9_C0036_7fec0db2"],
    reason: "Removed the unsupported essential-medicine-status requirement and retained the directly evidenced availability-risk and mitigation concepts.",
  },
  "gapfill:TB002": {
    query: "In ICH Q3C Table 2, why should Class 2 solvents be limited, how are PDE and concentration values rounded, and what analytical-precision caveat applies?",
    gold: ["ich_q3c_r9_C0019_a930f0fe"],
    reason: "Replaced the incomplete request for every solvent and limit with table-level facts preserved in the frozen excerpt.",
  },
  "gapfill:TB008": {
    query: "In the ICH Q3A examples for maximum daily doses of 0.5 g and 0.8 g, what reporting, identification, and qualification thresholds are shown, and how should percentage versus TDI thresholds be compared?",
    gold: ["ich_q3a_r2_C0024_91dabced", "ich_q3a_r2_C0025_f9728ab8"],
    reason: "Narrowed the question from universal dose-dependent thresholds to the two complete numerical examples available in the frozen evidence.",
  },
};

try {
  await fs.access(outputPath);
  throw new Error(`refusing to overwrite existing revision pack: ${outputPath}`);
} catch (error) {
  if (error?.code !== "ENOENT") throw error;
}

const round1 = JSON.parse(await fs.readFile(round1Path, "utf8"));
const sourceById = new Map(round1.queries.map((row) => [String(row.annotation_id), row]));
const rows = [];
for (const [originalId, revision] of Object.entries(revisions)) {
  const source = sourceById.get(originalId);
  if (!source || source.review_status !== "needs_revision") throw new Error(`missing needs-revision source: ${originalId}`);
  const candidates = new Set(source.candidate_evidence_chunk_ids || []);
  const outside = revision.gold.filter((chunkId) => !candidates.has(chunkId));
  if (outside.length) throw new Error(`revision gold outside reviewed candidates for ${originalId}: ${outside.join(", ")}`);
  rows.push({
    revision_id: `${originalId}__R1`,
    original_annotation_id: originalId,
    query_slice: source.query_slice,
    original_query: source.query,
    revised_query: revision.query,
    proposed_gold_evidence_chunk_ids: revision.gold,
    candidate_evidence_chunk_ids: source.candidate_evidence_chunk_ids,
    revision_reason: revision.reason,
    round1_reviewer_rationale: source.reviewer_rationale,
    review_status: "Pending",
    accepted_gold_evidence_chunk_ids: [],
    reviewer_rationale: "",
  });
}
const result = {
  schema_version: "1.0",
  status: "heldout_revision_round_requires_human_confirmation_do_not_execute",
  retrieval_execution_prohibited: true,
  source_round1_pack: round1Path,
  revision_count: rows.length,
  revisions: rows,
};
await fs.writeFile(outputPath, JSON.stringify(result, null, 2), "utf8");
console.log(JSON.stringify({ outputPath, revision_ids: rows.map((row) => row.revision_id) }, null, 2));
