import * as path from 'path';

export const DEFAULT_QAGE_ARTIFACT_DIRS = ['qodeyard', 'briq.d', 'exeq.d', 'reqap.d', 'bloq.d'] as const;

export function isPathInside(parentPath: string, candidatePath: string): boolean {
    if (!candidatePath || !parentPath) return false;
    const resolvedParent = path.resolve(parentPath);
    const resolvedCandidate = path.resolve(candidatePath);
    const relative = path.relative(resolvedParent, resolvedCandidate);
    return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative));
}

export function isPathContained(candidatePath: string, basePath: string): boolean {
    return isPathInside(basePath, candidatePath);
}

export function isAllowedQageArtifactPath(
    candidatePath: string,
    qageRoot: string,
    artifactDirs: readonly string[] = DEFAULT_QAGE_ARTIFACT_DIRS
): boolean {
    if (!candidatePath || !qageRoot) return false;
    for (const dir of artifactDirs) {
        if (isPathContained(candidatePath, path.join(qageRoot, dir))) {
            return true;
        }
    }
    return false;
}
