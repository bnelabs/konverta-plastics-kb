export interface Material {
  code: string;
  name: string;
  common_uses: string;
  melt_temp_c: string;
  density_g_cm3: number | null;
  toxicity_level: string;
  recyclability: string;
  notes: string;
  source_title: string;
  source_url: string;
  review_status: 'draft' | 'verified';
}

export function validateSourceUrl(url: string): boolean {
  try {
    const u = new URL(url);
    return u.protocol === 'https:';
  } catch {
    return false;
  }
}

export function validateMaterial(m: Partial<Material>): string[] {
  const errors: string[] = [];
  if (!m.code || !/^[A-Z0-9-]+$/.test(m.code)) errors.push('Invalid code');
  if (!m.source_title || m.source_title.trim().length < 2) errors.push('Source title required');
  if (!m.source_url || !validateSourceUrl(m.source_url)) errors.push('Source URL must be https');
  if (!m.review_status || !['draft','verified'].includes(m.review_status)) errors.push('Invalid review status');
  return errors;
}
