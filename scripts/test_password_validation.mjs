// Unit checks of the production rules/listeners; browser acceptance is separate.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../custom_addons/b2b_website/static/src/js/password_validation.js', import.meta.url), 'utf8')
    .replace(/^import .*;\r?\n/gm, '').replaceAll('export function ', 'function ');
const message = 'Use at least 8 characters, including a letter and a number.';
const errors = {password_error: {textContent: ''}, confirm_password_error: {textContent: ''}};
const listeners = {};
const form = {dataset: {}, addEventListener: (name, fn) => {listeners[name] = fn;},
    querySelector: selector => selector === 'input[data-lt-password-confirm]' ? confirmation : errors[selector.slice(1)]};
function field(id) {
    return {id, value: '', form, dataset: {}, listeners: {},
        addEventListener(name, fn) {this.listeners[name] = fn;},
        setCustomValidity(value) {this.validity = value;},
        setAttribute(name, value) {this[name] = value;}, focus() {this.focused = true;}};
}
const password = field('password'), confirmation = field('confirm_password');
password.dataset = {ltPasswordPolicy: '8', ltLetterNumber: '1', ltPasswordMessage: message};
const context = vm.createContext({_t: value => value, document: {querySelectorAll: () => [password]}});
vm.runInContext(source + '\nglobalThis.rule = passwordPolicyError; globalThis.initialize = initializePasswordValidation;', context);

for (const value of ['abc1234', 'abcdefgh', '12345678', '!!!!!!!!', 'abc!!!!!', '１２３４５６７８']) {
    assert.equal(context.rule(value, 8, true, message), message);
}
for (const value of ['abcd1234', '1abcdefg', 'ABCD1234', 'Ab12!@#$', ' long password 123! ', 'abc1😀😀😀😀']) {
    assert.equal(context.rule(value, 8, true, message), '');
}
assert.equal(context.rule('abc1😀😀😀', 8, true, message), message);
assert.equal(context.rule('abcd1234', 12, true, '12 characters'), '12 characters');
assert.equal(context.rule('abcdefgh', 8, false, '8 characters'), '');
assert.equal(context.rule('', 8, true, message), 'Please enter a password.');

context.initialize();
password.value = 'abcdefgh';
password.listeners.blur();
assert.equal(errors.password_error.textContent, message);
let prevented = false;
listeners.invalid({target: password, preventDefault() {prevented = true;}});
assert.equal(prevented, true);
password.value = confirmation.value = 'abcd1234';
password.listeners.input();
confirmation.listeners.input();
assert.equal(errors.password_error.textContent, '');
assert.equal(errors.confirm_password_error.textContent, '');
confirmation.value = 'different123';
let stopped = false;
listeners.submit({preventDefault() {prevented = true;}, stopImmediatePropagation() {stopped = true;}});
assert.equal(stopped, true);
assert.equal(confirmation.focused, true);
assert.equal(errors.confirm_password_error.textContent, 'Passwords do not match; please retype them.');
confirmation.value = password.value;
stopped = false;
listeners.submit({preventDefault() {throw Error('Valid password blocked');}, stopImmediatePropagation() {stopped = true;}});
assert.equal(stopped, false);
context.initialize(); // Re-initialization must not duplicate listeners.
assert.equal(form.dataset.ltPasswordsInitialized, '1');
console.log('Password rules: 16 cases passed; inline/invalid/submit/recovery listeners passed.');
