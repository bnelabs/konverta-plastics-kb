export function validateSourceUrl(url) {
    try {
        const u = new URL(url);
        return u.protocol === 'https:';
    }
    catch {
        return false;
    }
}
export function validateMaterial(m) {
    const errors = [];
    if (!m.code || !/^[A-Z0-9-]+$/.test(m.code))
        errors.push('Invalid code');
    if (!m.source_title || m.source_title.trim().length < 2)
        errors.push('Source title required');
    if (!m.source_url || !validateSourceUrl(m.source_url))
        errors.push('Source URL must be https');
    if (!m.review_status || !['draft', 'verified'].includes(m.review_status))
        errors.push('Invalid review status');
    return errors;
}
