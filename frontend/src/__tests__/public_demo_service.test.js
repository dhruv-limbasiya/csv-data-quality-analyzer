import { describe, expect, it } from 'vitest';
import { publicDemoService } from '../services/publicDemoService';

describe('Public demo data services', () => {
  it('returns synthetic sample datasets and preview rows without API access', async () => {
    const result = await publicDemoService.listDatasets();
    expect(result.total).toBeGreaterThan(0);
    expect(result.items[0].original_filename).toBe('customers_q3_raw.csv');
    expect(result.items[0].user_id).toBe(0);

    const detail = await publicDemoService.getDataset(result.items[0].id);
    expect(detail.preview_rows[0].email).toBe('ava@example.com');
  });

  it('provides illustrative quality analysis for sample datasets', async () => {
    const result = await publicDemoService.getDatasetAnalyses(1);
    expect(result.total).toBe(1);
    expect(result.items[0].overall_score).toBe(84.5);
    expect(result.items[0].summary_stats.columns_quality).toContainEqual({
      name: 'income',
      missing_percentage: 8.5,
    });
  });

  it('previews and records cleaning changes only in demo memory', async () => {
    const config = {
      whitespace_cleaning: { enabled: true, trim_whitespace: true },
      duplicate_removal: { enabled: true, keep: 'first', subset_columns: ['full_name', 'email'] },
    };
    const preview = await publicDemoService.previewCleaning(1, config);
    expect(preview.demo_only).toBe(true);
    expect(preview.original_preview[0].full_name).toBe('  Ava Patel ');
    expect(preview.cleaned_preview[0].full_name).toBe('Ava Patel');
    expect(preview.summary.rows.after).toBeLessThan(preview.summary.rows.before);

    const record = await publicDemoService.applyCleaning(1, config);
    expect(record.status).toBe('demo-only');
    expect(record.demo_only).toBe(true);

    const history = await publicDemoService.getDatasetCleanings(1);
    expect(history.items[0].id).toBe(record.id);
    expect(history.items[0].user_id).toBe(0);
  });

  it('rejects uploads and unknown datasets instead of reporting success', async () => {
    await expect(publicDemoService.uploadDataset({ name: 'private.csv' }))
      .rejects.toThrow('CSV uploads are disabled in the public demo.');
    await expect(publicDemoService.getDataset(999))
      .rejects.toThrow('That sample dataset is not available in the public demo.');
  });

  it('explains transformations that the browser-only demo does not support', async () => {
    await expect(publicDemoService.previewCleaning(1, {
      outlier_handling: { enabled: true },
    })).rejects.toThrow('not enabled in the browser-only public demo');
  });
});
