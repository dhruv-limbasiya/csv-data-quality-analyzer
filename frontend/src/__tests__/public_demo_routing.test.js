import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}));

vi.mock('../config/publicDemo', () => ({ PUBLIC_DEMO_MODE: true }));
vi.mock('../services/api', () => ({ default: apiMocks }));

import { datasetService } from '../services/datasetService';
import { analysisService } from '../services/analysisService';
import { cleaningService } from '../services/cleaningService';

describe('Service routing in public demo mode', () => {
  beforeEach(() => {
    Object.values(apiMocks).forEach((mock) => mock.mockReset());
  });

  it('uses synthetic datasets, analysis, and cleaning without calling the backend', async () => {
    const datasets = await datasetService.listDatasets();
    const analysis = await analysisService.runAnalysis(datasets.items[0].id);
    const preview = await cleaningService.previewCleaning(datasets.items[0].id, {});

    expect(datasets.items).toHaveLength(3);
    expect(analysis.overall_score).toBe(84.5);
    expect(preview.demo_only).toBe(true);
    expect(Object.values(apiMocks).every((mock) => mock.mock.calls.length === 0)).toBe(true);
  });

  it('rejects uploads instead of sending them to real storage', async () => {
    await expect(datasetService.uploadDataset({ name: 'visitor.csv' }))
      .rejects.toThrow('CSV uploads are disabled in the public demo.');
    expect(Object.values(apiMocks).every((mock) => mock.mock.calls.length === 0)).toBe(true);
  });
});
