import { resumeExportFilename } from "@/lib/exportFilename";

function assert(condition: boolean, message: string) {
  if (!condition) throw new Error(`FAIL: ${message}`);
  console.log(`  PASS: ${message}`);
}

console.log("exportFilename tests");

assert(
  resumeExportFilename("Jane Doe", "pdf", {
    hasJd: true,
    companyName: "Acme Corp",
  }) === "acme_corp_resume.pdf",
  "uses company name when tailoring to a JD",
);

assert(
  resumeExportFilename("Jane Doe", "pdf", {
    hasJd: false,
    companyName: "—",
  }) === "jane_doe_resume.pdf",
  "uses candidate name when there is no JD",
);

assert(
  resumeExportFilename("Jane Doe", "pdf", {
    hasJd: true,
    companyName: "Unknown",
  }) === "jane_doe_resume.pdf",
  "falls back to candidate name when company is unknown",
);

assert(
  resumeExportFilename(undefined, "docx", { hasJd: false }) === "resume_resume.docx",
  "falls back to resume when no names are available",
);

console.log("All exportFilename tests passed.");
