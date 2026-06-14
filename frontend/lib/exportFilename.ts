function slug(text: string): string {
  return (
    text
      .trim()
      .toLowerCase()
      .replace(/[^\w\-]+/g, "_")
      .replace(/^_|_$/g, "")
      .slice(0, 60) || "resume"
  );
}

export function resumeExportFilename(
  candidateName: string | undefined,
  ext: "pdf" | "docx" | "txt",
  options?: { companyName?: string; hasJd?: boolean },
): string {
  const hasJd = options?.hasJd ?? false;
  const company = options?.companyName?.trim();
  const useCompany =
    hasJd && company && company !== "—" && company.toLowerCase() !== "unknown";

  const base = useCompany ? slug(company) : slug(candidateName?.trim() || "") || "resume";
  return `${base}_resume.${ext}`;
}
