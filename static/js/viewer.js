/* PocketDock 3Dmol.js viewer utilities */

/**
 * Convert PDBQT text to a PDB-like format that 3Dmol can render.
 * Strips the charge and AD type columns.
 */
function pdbqtToPdb(pdbqtText) {
    const lines = pdbqtText.split('\n');
    const pdbLines = [];
    for (const line of lines) {
        if (line.startsWith('ATOM') || line.startsWith('HETATM')) {
            pdbLines.push(line.substring(0, 66).trimEnd());
        } else if (line.startsWith('END') || line.startsWith('TER')) {
            pdbLines.push(line.trimEnd());
        }
    }
    return pdbLines.join('\n');
}

/**
 * Color mapping for pocket probability.
 * Higher probability -> more red, lower -> blue.
 */
function probabilityToColor(prob) {
    const r = Math.round(255 * prob);
    const b = Math.round(255 * (1 - prob));
    const g = Math.round(100 * (1 - Math.abs(prob - 0.5) * 2));
    return `rgb(${r},${g},${b})`;
}
