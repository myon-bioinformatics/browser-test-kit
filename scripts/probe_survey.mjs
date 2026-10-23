/** Node twin of probe_survey.py. No runtime dependencies; same rules and same output as the Python module.
 * scripts/twin_parity.py checks the two agree. Node cannot tell 1.0 from 1, so send integers.
 */
import {envelope, finding} from './probe_evidence.mjs';

const COLLECTION = ['complete', 'partial', 'unknown'];

function count(name, value) {
  if (value === null || value === undefined) return null;
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) {
    throw new TypeError(`${name} must be a non-negative integer or null`);
  }
  return value;
}

export function summarize(snapshot) {
  if (!snapshot || typeof snapshot !== 'object' || Array.isArray(snapshot)) throw new TypeError('snapshot must be an object');
  const interactive = snapshot.interactive;
  if (!interactive || typeof interactive !== 'object' || Array.isArray(interactive)) {
    throw new TypeError('interactive must be an object');
  }
  const n = count('interactive.count', interactive.count);
  const collection = interactive.collection;
  if (!COLLECTION.includes(collection)) throw new TypeError(`interactive.collection must be one of ${COLLECTION.join(', ')}`);
  const shadow = count('shadow_roots', snapshot.shadow_roots);
  const frames = count('frames', snapshot.frames);

  const item = n === null
    ? finding('interactive elements: not counted', 'dom:interactive', 'unknown', ['count not collected'])
    : finding(`interactive elements: ${n}`, 'dom:interactive', collection,
        collection === 'complete' ? [] : [`collection ${collection}`]);

  const skipped = [];
  if (shadow !== 0) skipped.push(shadow === null ? 'shadow roots: not counted' : `shadow roots (${shadow}): not entered`);
  if (frames !== 0) skipped.push(frames === null ? 'child frames: not counted' : `child frames (${frames}): not entered`);
  return envelope(snapshot.origin, [item], skipped);
}
