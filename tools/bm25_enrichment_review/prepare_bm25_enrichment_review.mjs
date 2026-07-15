import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";

const root = process.env.PROJECT_ROOT || "D:/Projects/financial knowledge graph";
const corpusDir = path.join(root, "data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4");
const outputDir = path.join(root, "outputs/bm25_enrichment_heldout_review_2026-07-15");
const outputPath = path.join(root, "data/eval/bm25_enrichment_heldout_review_candidates_2026-07-15.json");
const reviewDataPath = path.join(outputDir, "review_workbook_data.json");
const priorPacks = [
  path.join(root, "data/eval/three_path_evaluation_frozen_2026-07-15.json"),
  path.join(root, "data/eval/adaptive_text_first_heldout_frozen_run_ready_2026-07-15.json"),
];

const candidates = [
  { id: "BA-SC01", slice: "single_clause", q: "What elements should a pharmaceutical change-management system include when evaluating, approving, implementing, and reviewing a proposed change?", gold: ["ich_q10_C0016_192f9b01"] },
  { id: "BA-SC02", slice: "single_clause", q: "What information can be used to justify the selection of a proposed starting material for a synthetic drug substance?", gold: ["ich_q11_C0033_3c8a98e7"] },
  { id: "BA-SC03", slice: "single_clause", q: "How should communication and change management be coordinated across multiple stakeholders, sites, and quality systems in a pharmaceutical supply chain?", gold: ["ich_q12_C0044_cf8b05ce"] },
  { id: "BA-SC04", slice: "single_clause", q: "Which approaches may be used to define batch size in continuous manufacturing, and what must be justified when a batch-size range is proposed?", gold: ["ich_q13_C0006_dc89320f"] },
  { id: "BA-SC05", slice: "single_clause", q: "How does ICH Q14 define analytical-procedure robustness, and when may robustness studies performed during development avoid repetition during validation?", gold: ["ich_q14_C0016_7e8701ba"] },
  { id: "BA-SC06", slice: "single_clause", q: "How should model viruses be selected and used in viral-clearance studies, and how many viruses with differing characteristics are generally assessed?", gold: ["ich_q5a_r2_C0063_edfa5494"] },
  { id: "BA-SC07", slice: "single_clause", q: "What is a pharmaceutical specification, what does conformance to it mean, and what role does it play in regulatory approval?", gold: ["ich_q6a_C0023_3a1c63c0"] },
  { id: "BA-SC08", slice: "single_clause", q: "What controls should apply to the issuance, use, retention, and revision history of master production instructions for APIs and intermediates?", gold: ["ich_q7_C0031_7c52c707"] },
  { id: "BA-SC09", slice: "single_clause", q: "How should a pharmaceutical quality system approve and oversee outsourced activities and material suppliers over the product lifecycle?", gold: ["ich_q9_C0039_5541525e"] },
  { id: "BA-SC10", slice: "single_clause", q: "How are primary, production, and ongoing stability batches defined for a finished pharmaceutical product?", gold: ["who_stability_q1f_C0042_3372fadc"] },

  { id: "BA-TB01", slice: "table", q: "For drug products in semi-permeable containers, what storage conditions and minimum data periods are specified for long-term, intermediate, and accelerated stability studies?", gold: ["ich_q1a_C0032_7aeda7d5"] },
  { id: "BA-TB02", slice: "table", q: "In the ICH Q1D bracketing example, which strength, batch, and container-size combinations are tested and which intermediate combinations are omitted?", gold: ["ich_q1d_C0015_e39f3d1c"] },
  { id: "BA-TB03", slice: "table", q: "What reportable ranges are recommended for assay, content-uniformity, dissolution, impurity, and potency analytical procedures in ICH Q2(R2)?", gold: ["ich_q2r2_C0013_0057ab10"] },
  { id: "BA-TB04", slice: "table", q: "How does ICH Q3D classify elemental impurities by toxicity and occurrence, and for which administration routes is risk assessment required for each class?", gold: ["ich_q3d_r2_C0024_afc5bc1b"] },
  { id: "BA-TB05", slice: "table", q: "What viral testing is required at the master cell bank, working cell bank, and cells at the limit of in-vitro cell age?", gold: ["ich_q5a_r2_C0055_af4c166b"] },
  { id: "BA-TB06", slice: "table", q: "How is the process-performance and product-quality monitoring system applied across pharmaceutical development, technology transfer, commercial manufacturing, and product discontinuation?", gold: ["ich_q10_C0013_535f4ed9"] },
  { id: "BA-TB07", slice: "table", q: "For a long continuous-manufacturing run, what controls are proposed for cleaning and fouling, in-process material stability, process drift, and equipment maintenance?", gold: ["ich_q13_C0065_1335fd65"] },
  { id: "BA-TB08", slice: "table", q: "What performance characteristics and acceptance criteria are illustrated for the anti-TNF-alpha bioassay in the ICH Q14 example?", gold: ["ich_q14_C0114_af2cc69a"] },

  { id: "BA-DS01", slice: "document_structure", q: "Which ICH M7 sections should be navigated to retrieve requirements for impurity assessment, hazard assessment, risk characterization, and control approaches?", gold: ["ich_m7_r2_C0019_56edfa94", "ich_m7_r2_C0024_3c9c2d26", "ich_m7_r2_C0025_68f4454a", "ich_m7_r2_C0041_97a64829"] },
  { id: "BA-DS02", slice: "document_structure", q: "Which ICH Q3D sections should be navigated to identify potential elemental-impurity sources, evaluate identified risks, establish controls, and manage risks across the product lifecycle?", gold: ["ich_q3d_r2_C0018_9bcf18a5", "ich_q3d_r2_C0020_ec3a0fa8", "ich_q3d_r2_C0027_aa089226", "ich_q3d_r2_C0031_ef8a84f6", "ich_q3d_r2_C0042_96843691"] },
  { id: "BA-DS03", slice: "document_structure", q: "Which ICH Q5A(R2) sections should be consulted for virus testing and for evaluating viral clearance in the manufacturing process?", gold: ["ich_q5a_r2_C0084_93ae2544", "ich_q5a_r2_C0088_77b57603", "ich_q5a_r2_C0089_c41bbf97"] },
  { id: "BA-DS04", slice: "document_structure", q: "Which ICH Q6B sections organize requirements for product characterization, justification of specifications, drug-substance specifications, and drug-product specifications?", gold: ["ich_q6b_C0008_7555c936", "ich_q6b_C0026_2929f6ff", "ich_q6b_C0030_ec652f71", "ich_q6b_C0036_adceea47"] },
  { id: "BA-DS05", slice: "document_structure", q: "Which ICH Q12 sections should be consulted to identify and revise established conditions and to define the content and use of a post-approval change management protocol?", gold: ["ich_q12_C0018_fe6c0a58", "ich_q12_C0026_7d44c459", "ich_q12_C0028_cf122ff8", "ich_q12_C0032_1f4f8f5b"] },
  { id: "BA-DS06", slice: "document_structure", q: "Which ICH Q14 sections should be navigated for the analytical target profile, analytical-procedure control strategy, established conditions, and lifecycle management of post-approval changes?", gold: ["ich_q14_C0013_f3a85d0e", "ich_q14_C0021_f0411bee", "ich_q14_C0023_ebefd70f", "ich_q14_C0025_42359d92"] },

  { id: "BA-CD01", slice: "cross_document", q: "Across ICH Q10 and ICH Q12, what controls should be applied before and after a pharmaceutical change is implemented to ensure that its objective is achieved without unintended product-quality consequences?", gold: ["ich_q10_C0015_270983de", "ich_q12_C0059_0a491636", "ich_q12_C0060_6f7d62f3"] },
  { id: "BA-CD02", slice: "cross_document", q: "How do ICH Q7 and ICH Q11 define an API starting material and require the selection of a suitable point at which the drug-substance manufacturing process begins?", gold: ["ich_q7_C0109_27f16c65", "ich_q11_C0027_029fe86f"] },
  { id: "BA-CD03", slice: "cross_document", q: "Across ICH Q7 and ICH Q9, what risk-based controls are expected for approving, monitoring, and periodically reassessing suppliers of critical materials?", gold: ["ich_q7_C0041_5e8cf945", "ich_q9_C0039_5541525e"] },
  { id: "BA-CD04", slice: "cross_document", q: "How do ICH Q2(R2) and ICH Q14 describe robustness testing for an analytical procedure, including deliberate parameter variations and sample or reagent stability?", gold: ["ich_q2r2_C0055_00ba5a6d", "ich_q14_C0016_7e8701ba"] },
  { id: "BA-CD05", slice: "cross_document", q: "What ongoing stability-study commitments are expected when the available long-term data do not yet cover the proposed retest period for an API under ICH Q1A(R2) and WHO guidance?", gold: ["ich_q1a_C0019_73df0a2c", "who_stability_q1f_C0020_c0210003"] },
  { id: "BA-CD06", slice: "cross_document", q: "How should process dynamics and potential disturbances be considered when designing viral-clearance controls for continuous manufacturing under ICH Q5A(R2) and ICH Q13?", gold: ["ich_q5a_r2_C0010_42142748", "ich_q13_C0009_7fc1ccb9"] },
];

function collectGold(pack) {
  return new Set((pack.queries || []).flatMap((row) => row.gold_evidence_chunk_ids || []));
}

function stripHtml(html) {
  return String(html || "")
    .replace(/<\/(td|th)>/gi, "\t")
    .replace(/<\/tr>/gi, "\n")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/[ \t]+\n/g, "\n")
    .trim();
}

const chunkStore = new Map();
const tableStore = new Map();
for (const fileName of (await fs.readdir(corpusDir)).sort()) {
  const filePath = path.join(corpusDir, fileName);
  if (fileName.endsWith("_enriched.json")) {
    for (const row of JSON.parse(await fs.readFile(filePath, "utf8"))) {
      if (row.chunk_id) chunkStore.set(String(row.chunk_id), { ...row, frozen_source_file: filePath });
    }
  }
  if (fileName.endsWith("_tables.json")) {
    for (const row of JSON.parse(await fs.readFile(filePath, "utf8"))) {
      const id = String(row.chunk_id || "");
      if (!id) continue;
      if (!tableStore.has(id)) tableStore.set(id, []);
      tableStore.get(id).push({ table_source_text: stripHtml(row.table), table_summary: row.table_summary || "" });
    }
  }
}

const priorGold = new Set();
for (const filePath of priorPacks) {
  const pack = JSON.parse(await fs.readFile(filePath, "utf8"));
  for (const id of collectGold(pack)) priorGold.add(id);
}

const errors = [];
const seenIds = new Set();
for (const row of candidates) {
  if (seenIds.has(row.id)) errors.push(`${row.id}: duplicate review ID`);
  seenIds.add(row.id);
  if (!row.q.trim()) errors.push(`${row.id}: empty question`);
  if (!row.gold.length) errors.push(`${row.id}: empty proposed gold set`);
  const docs = new Set();
  for (const id of row.gold) {
    const chunk = chunkStore.get(id);
    if (!chunk) errors.push(`${row.id}: missing chunk ${id}`);
    else {
      docs.add(chunk.doc_id);
      if (!String(chunk.content || "").trim()) errors.push(`${row.id}: empty source passage ${id}`);
    }
    if (priorGold.has(id)) errors.push(`${row.id}: prior-gold overlap ${id}`);
  }
  if (row.slice === "cross_document" && docs.size < 2) errors.push(`${row.id}: cross-document row has fewer than two documents`);
  if (row.slice === "table" && !row.gold.some((id) => tableStore.has(id))) errors.push(`${row.id}: table row has no frozen table record`);
}
const quota = Object.fromEntries(["single_clause", "table", "document_structure", "cross_document"].map((slice) => [slice, candidates.filter((row) => row.slice === slice).length]));
const expectedQuota = { single_clause: 10, table: 8, document_structure: 6, cross_document: 6 };
for (const [slice, expected] of Object.entries(expectedQuota)) if (quota[slice] !== expected) errors.push(`${slice}: expected ${expected}, found ${quota[slice]}`);
if (candidates.length !== 30) errors.push(`expected 30 rows, found ${candidates.length}`);

if (errors.length) {
  console.error(JSON.stringify({ status: "invalid", quota, errors }, null, 2));
  process.exit(1);
}

const queries = candidates.map((row) => ({
  review_id: row.id,
  query_slice: row.slice,
  question: row.q,
  proposed_gold_evidence_chunk_ids: row.gold,
  review_status: "Pending",
  revised_question: "",
  final_gold_evidence_chunk_ids: row.gold,
  reviewer_note: "",
  evidence: row.gold.map((id, index) => {
    const chunk = chunkStore.get(id);
    const tables = tableStore.get(id) || [];
    return {
      evidence_order: index + 1,
      chunk_id: id,
      doc_id: chunk.doc_id || "",
      heading: chunk.heading || "",
      parents_context: chunk.parents_context || "",
      frozen_source_file: chunk.frozen_source_file,
      original_source_passage: chunk.content || "",
      table_source_text: tables.map((item) => item.table_source_text).filter(Boolean).join("\n\n--- NEXT TABLE ---\n\n"),
      table_summary_reference_only: tables.map((item) => item.table_summary).filter(Boolean).join("\n\n"),
    };
  }),
}));

const pack = {
  schema_version: "1.0",
  status: "candidate_human_review_required",
  formal_metrics_ready: false,
  retrieval_execution_prohibited: true,
  created_at_utc: new Date().toISOString(),
  purpose: "Independent held-out set for BM25 baseline and corpus-enrichment ablation.",
  quota,
  independence_checks: {
    prior_frozen_packs: priorPacks,
    prior_gold_chunk_count: priorGold.size,
    prior_gold_overlap_count: 0,
    hyde_questions_used_as_test_questions: false,
  },
  queries,
};
const canonical = JSON.stringify(pack);
pack.candidate_content_sha256 = crypto.createHash("sha256").update(canonical).digest("hex");

await fs.mkdir(path.dirname(outputPath), { recursive: true });
await fs.mkdir(outputDir, { recursive: true });
await fs.writeFile(outputPath, JSON.stringify(pack, null, 2), "utf8");
await fs.writeFile(reviewDataPath, JSON.stringify({ generated_from: outputPath, pack }, null, 2), "utf8");
console.log(JSON.stringify({ status: "valid", outputPath, reviewDataPath, rows: queries.length, evidence_rows: queries.reduce((n, row) => n + row.evidence.length, 0), quota }, null, 2));
