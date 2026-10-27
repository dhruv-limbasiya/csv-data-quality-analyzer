import api from './api';
import { PUBLIC_DEMO_MODE } from '../config/publicDemo';
import { publicDemoService } from './publicDemoService';

export const analysisService = {
  /**
   * Run quality analysis on dataset
   */
  async runAnalysis(datasetId) {
    if (PUBLIC_DEMO_MODE) return publicDemoService.runAnalysis(datasetId);
    const res = await api.post(`/api/datasets/${datasetId}/analyze`);
    return res.data;
  },

  /**
   * Get all quality analyses for a dataset
   */
  async getDatasetAnalyses(datasetId, skip = 0, limit = 50) {
    if (PUBLIC_DEMO_MODE) return publicDemoService.getDatasetAnalyses(datasetId, skip, limit);
    const res = await api.get(`/api/datasets/${datasetId}/analyses`, {
      params: { skip, limit },
    });
    return res.data; // { total: int, items: [...] }
  },

  /**
   * Get specific analysis record by ID
   */
  async getAnalysis(analysisId) {
    if (PUBLIC_DEMO_MODE) return publicDemoService.getAnalysis(analysisId);
    const res = await api.get(`/api/analyses/${analysisId}`);
    return res.data;
  },
};
