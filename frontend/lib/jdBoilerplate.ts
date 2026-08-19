/** ATS trailing sections that never help resume tailoring. */
const BOILERPLATE_CUT_MARKERS: RegExp[] = [
  /\n\s*Physical Demands\s*:/i,
  /\n\s*Equal Opportunity Employer\b/i,
  /\n\s*Company Profile\s*:/i,
  /\n\s*Know Your Rights\b/i,
  /\n\s*EEO\s*(Statement|Policy)\b/i,
];

/** Drop Physical Demands / EEO / company fluff when present after real JD body. */
export function stripJdBoilerplate(text: string): string {
  let cutAt = -1;
  for (const marker of BOILERPLATE_CUT_MARKERS) {
    const match = marker.exec(text);
    if (match && match.index >= 800) {
      if (cutAt < 0 || match.index < cutAt) cutAt = match.index;
    }
  }
  return cutAt > 0 ? text.slice(0, cutAt).trim() : text;
}
