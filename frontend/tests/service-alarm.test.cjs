/* Pure local-clock regression tests using the project's existing TypeScript. */
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const source = fs.readFileSync(path.join(__dirname, '../src/lib/service-alarm.ts'), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
}}).outputText;
const exported = {};
vm.runInNewContext(js, { exports: exported }, { timeout: 1000 });
const { currentServiceLight: rowLight, currentPanelLight: panelLight } = exported;
const now = Date.parse('2026-10-11T15:00:00Z');
const iso = (offset) => new Date(now + offset).toISOString();
const alarm = (light, evidence_mode = 'DYNAMIC', valid_until_utc = iso(1000)) =>
  ({ light, evidence_mode, valid_until_utc });
const row = () => ({ alarm: alarm('GREEN'), evidence_utc: iso(-10000) });

test('a cached green row and its panel expire at the row deadline', () => {
  assert.equal(rowLight(row(), true, now + 1000), 'GREEN');
  assert.equal(rowLight(row(), true, now + 1001), 'RED');
  assert.equal(panelLight([row()], alarm('GREEN'), true, now + 1001), 'RED');
});
test('canonical server deadline wins over a later copied row deadline', () => {
  assert.equal(rowLight({ ...row(), valid_until_utc: iso(999999) }, true, now + 1001), 'RED');
});
test('missing or malformed dynamic expiry cannot display green', () => {
  for (const expiry of [null, 'malformed', '2026-10-11T15:01:00']) {
    assert.equal(rowLight({ alarm: alarm('GREEN', 'DYNAMIC', expiry) }, true, now), 'AMBER');
  }
});
test('future evidence and invalid observation clock cannot display green', () => {
  assert.equal(rowLight({ ...row(), evidence_utc: iso(1) }, true, now), 'AMBER');
  assert.equal(rowLight(row(), true, NaN), 'AMBER');
});
test('known fault survives stale observation; other old lights lose qualification', () => {
  assert.equal(rowLight({ alarm: alarm('RED') }, false, now), 'RED');
  for (const light of ['GREEN', 'BLUE', 'AMBER']) {
    assert.equal(rowLight({ alarm: alarm(light) }, false, now), 'AMBER');
  }
  assert.equal(panelLight([{ alarm: alarm('RED') }], alarm('GREEN'), false, now), 'RED');
});
test('current static and calendar proofs keep server-qualified semantics', () => {
  for (const mode of ['STATIC_PROOF', 'SESSION_DATA']) {
    assert.equal(rowLight({ alarm: alarm('GREEN', mode, null) }, true, now), 'GREEN');
  }
  assert.equal(rowLight({ alarm: alarm('GREEN', 'UNSUPPORTED', null) }, true, now), 'AMBER');
});
test('declared idle expires at its own active-window boundary', () => {
  const value = { alarm: alarm('GREEN', 'DECLARED_IDLE') };
  assert.equal(rowLight(value, true, now), 'GREEN');
  assert.equal(rowLight(value, true, now + 1001), 'RED');
});
test('empty, unknown and verified paused panels are distinct', () => {
  assert.equal(panelLight([], alarm('GREEN'), true, now), 'AMBER');
  assert.equal(panelLight([row()], alarm('AMBER'), true, now), 'AMBER');
  assert.equal(panelLight([{ alarm: alarm('BLUE') }], alarm('BLUE'), true, now), 'BLUE');
});
