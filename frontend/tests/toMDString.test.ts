import { describe, it, expect } from 'vitest';
import toMDString from '../src/lib/toMDString';

describe('toMDString', () => {
  it('converts primitives to strings', () => {
    expect(toMDString('hello')).toBe('hello');
    expect(toMDString(42)).toBe('42');
    expect(toMDString(true)).toBe('true');
    expect(toMDString(null)).toBe('');
    expect(toMDString(undefined)).toBe('');
  });

  it('joins arrays with newlines', () => {
    expect(toMDString(['a', 1, false])).toBe('a\n1\nfalse');
  });

  it('formats objects as fenced JSON', () => {
    const obj = { a: 1, b: 'two' };
    const expected = '```json\n' + JSON.stringify(obj, null, 2) + '\n```';
    expect(toMDString(obj)).toBe(expected);
  });
});
