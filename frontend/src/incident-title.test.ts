import { describe, expect, it } from 'vitest';
import { incidentTitle } from './incident-title';

describe('incident report headings', () => {
  it('uses the provided address and reported reason', () => {
    expect(incidentTitle('theres a tree blocking 54 george street', 'INFRASTRUCTURE'))
      .toBe('54 George Street — Tree blocking roadway');
  });
  it('preserves the difference between a reported person and an established fact', () => {
    expect(incidentTitle('there is a dead body in the street on 56 george street', 'MEDICAL'))
      .toBe('56 George Street — Person reported unresponsive or deceased');
  });
  it('does not invent a location when none is mentioned', () => {
    expect(incidentTitle('Tree blocking the road', 'INFRASTRUCTURE'))
      .toBe('Tree blocking roadway');
  });
});
