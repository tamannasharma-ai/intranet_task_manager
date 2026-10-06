// Unit tests with a fake speech service: no microphone or network access.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');
const source = fs.readFileSync('app/static/vendor/task-interactions.js', 'utf8').split('const commentsDialog =')[0];

function setup({supported = true, secure = true, maxLength = 200} = {}) {
  class Element {
    constructor() { this.value = ''; this.disabled = false; this.readOnly = false; this.listeners = {}; this.attributes = {}; this.children = []; }
    setAttribute(k, v) { this.attributes[k] = v; }
    addEventListener(k, v) { this.listeners[k] = v; }
    append(...children) { this.children.push(...children); }
    add(option) { if (!this.value) this.value = option.value; }
    after(...nodes) { this.afterNodes = nodes; }
    dispatchEvent() { this.inputEvents = (this.inputEvents || 0) + 1; }
    focus() {}
  }
  const field = new Element();
  const submit = new Element();
  field.maxLength = maxLength;
  field.form = {querySelector: () => submit};
  let recognition;
  class Recognition {
    constructor() { recognition = this; }
    start() { this.started = true; }
    stop() { this.stopped = true; }
    abort() { this.aborted = true; }
  }
  const context = vm.createContext({
    window: {SpeechRecognition: supported ? Recognition : undefined, isSecureContext: secure},
    document: {getElementById: () => field, createElement: () => new Element()},
    Option: class {constructor(label, value) { this.value = value; }}, Event: class {}
  });
  vm.runInContext(source + '\naddVoiceControl("task-title");', context);
  const [row, status] = field.afterNodes;
  const [button, language] = row.children;
  return {field, submit, button, language, status, context, get recognition() {return recognition;}};
}
function result(recognition, words) {
  recognition.onresult({resultIndex: 0, results: words.map(text => Object.assign([{transcript: text}], {isFinal: true}))});
}

test('dictation appends once, uses selected language, and requires review before save', () => {
  const ui = setup(); ui.field.value = 'Existing'; ui.language.value = 'hi-IN';
  ui.button.listeners.click();
  assert.equal(ui.recognition.lang, 'hi-IN');
  assert.equal(ui.submit.disabled, true);
  result(ui.recognition, ['काम पूरा हुआ']);
  result(ui.recognition, ['काम पूरा हुआ']);
  assert.equal(ui.field.value, 'Existing काम पूरा हुआ');
  ui.button.listeners.click();
  assert.equal(ui.recognition.stopped, true);
  assert.equal(ui.submit.disabled, true);
  ui.recognition.onend();
  assert.equal(ui.submit.disabled, false);
  assert.equal(ui.field.readOnly, false);
  assert.match(ui.status.textContent, /Review/);
});
test('closing aborts recording and ignores late results', () => {
  const ui = setup(); ui.field.value = 'Draft'; ui.button.listeners.click();
  const recognition = ui.recognition;
  vm.runInContext('stopDictation()', ui.context);
  result(recognition, ['late result']);
  assert.equal(ui.field.value, 'Draft');
  assert.equal(recognition.aborted, true);
  assert.equal(ui.submit.disabled, false);
});
test('permission failure preserves text and restores controls', () => {
  const ui = setup(); ui.field.value = 'Draft'; ui.button.listeners.click();
  ui.recognition.onerror({error: 'not-allowed'});
  assert.equal(ui.field.value, 'Draft');
  assert.match(ui.status.textContent, /permission denied/);
  assert.equal(ui.field.readOnly, false);
  assert.equal(ui.submit.disabled, false);
});
test('unsupported browser and insecure host retain typing fallback', () => {
  for (const options of [{supported:false}, {secure:false}]) {
    const ui = setup(options);
    assert.equal(ui.button.disabled, true);
    assert.equal(ui.field.readOnly, false);
    assert.match(ui.status.textContent, /still type/);
  }
});
test('dictation respects field limit without truncating existing draft', () => {
  const ui = setup({maxLength:10}); ui.field.value = 'Draft'; ui.button.listeners.click();
  result(ui.recognition, ['too many words']);
  assert.equal(ui.field.value, 'Draft');
  assert.equal(ui.recognition.aborted, true);
  assert.match(ui.status.textContent, /field limit/);
});
test('cannot start microphone while comment submission holds the field', () => {
  const ui = setup(); ui.field.readOnly = true; ui.button.listeners.click();
  assert.equal(ui.recognition, undefined);
});
