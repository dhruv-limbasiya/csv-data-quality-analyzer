import api from './api';

export const datasetService = {
  /**
   * List datasets owned by current user
   */
  async listDatasets() {
    const res = await api.get('/api/datasets');
    return res.data; // { total: int, items: [...] }
  },

  /**
   * Get dataset metadata and sample preview rows
   */
  async getDataset(id) {
    const res = await api.get(`/api/datasets/${id}`);
    return res.data;
  },

  /**
   * Upload a CSV dataset (multipart/form-data)
   * onUploadProgress callback optional
   */
  async uploadDataset(file, onProgress) {
    const formData = new FormData();
    formData.append('file', file);

    const res = await api.post('/api/datasets/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          onProgress(percentCompleted);
        }
      },
    });
    return res.data;
  },
};
