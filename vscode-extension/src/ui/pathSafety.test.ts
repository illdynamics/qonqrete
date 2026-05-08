import * as assert from 'assert';
import * as path from 'path';

import { isAllowedQageArtifactPath, isPathContained, isPathInside } from './pathSafety';

function runPathSafetyTests(): void {
    const qageRoot = path.join('/tmp', 'workspace', 'worqspace', 'qage_20260505_120000');
    const insideFile = path.join(qageRoot, 'qodeyard', 'main.py');
    assert.strictEqual(isAllowedQageArtifactPath(insideFile, qageRoot), true, 'file inside qodeyard should be allowed');

    const traversal = path.join(qageRoot, 'qodeyard', '..', 'secret.txt');
    assert.strictEqual(isAllowedQageArtifactPath(traversal, qageRoot), false, '../ traversal should be rejected');

    const absoluteOutside = path.join('/tmp', 'workspace', 'outside', 'secret.py');
    assert.strictEqual(isAllowedQageArtifactPath(absoluteOutside, qageRoot), false, 'absolute path outside qage should be rejected');

    const siblingPrefixEscape = path.join('/tmp', 'workspace', 'worqspace', 'qage_20260505_120000_evil', 'qodeyard', 'main.py');
    assert.strictEqual(isAllowedQageArtifactPath(siblingPrefixEscape, qageRoot), false, 'sibling-prefix escape should be rejected');

    const normalizedEscape = path.join(qageRoot, 'qodeyard', 'nested', '..', '..', '..', 'secret.py');
    assert.strictEqual(isAllowedQageArtifactPath(normalizedEscape, qageRoot), false, 'normalized traversal escape should be rejected');

    assert.strictEqual(
        isPathContained('/tmp/qodeyard_evil/file.py', '/tmp/qodeyard'),
        false,
        'prefix-only containment must not pass'
    );

    assert.strictEqual(
        isPathInside(path.join(qageRoot, 'qodeyard'), insideFile),
        true,
        'isPathInside should allow true descendants'
    );
}

runPathSafetyTests();
console.log('pathSafety tests passed');
