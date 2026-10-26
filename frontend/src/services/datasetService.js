import api from './api';
import axios from 'axios';

const DIRECT_UPLOAD = import.meta.env.VITE_DIRECT_UPLOAD === 'true';

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
  async uploadDataset(file, onProgress, { signal } = {}) {
    if (DIRECT_UPLOAD) {
      const authorization = await api.post('/api/datasets/upload/authorize', {
        filename: file.name,
        size_bytes: file.size,
      });
      const { dataset_id: datasetId, upload_url: uploadUrl, required_headers: headers } = authorization.data;
      try {
        await axios.put(uploadUrl, file, {
          headers,
          withCredentials: false,
          signal,
          onUploadProgress: (progressEvent) => {
            if (onProgress && progressEvent.total) {
              onProgress(Math.round((progressEvent.loaded * 100) / progressEvent.total));
            }
          },
        });
        const finalized = await api.post(`/api/datasets/${datasetId}/finalize`);
        return finalized.data;
      } catch (error) {
        // Cancel the pending database row and best-effort delete its staging key.
        try {
          await api.delete(`/api/datasets/${datasetId}/upload`);
        } catch {
          // Expired staging objects are removed by the configured R2 lifecycle rule.
        }
        throw error;
      }
    }

    const formData = new FormData();
    formData.append('file', file);

    const res = await api.post('/api/datasets/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      signal,
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
