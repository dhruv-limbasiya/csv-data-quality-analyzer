import api from './api';

export const cleaningService = {
  /**
   * Preview cleaning transformations in memory (no disk/db write)
   */
  async previewCleaning(datasetId, config, previewLimit = 10) {
    const res = await api.post(`/api/datasets/${datasetId}/clean/preview`, {
      config,
      preview_limit: previewLimit,
    });
    return res.data;
  },

  /**
   * Apply cleaning and save permanent cleaned CSV file and PostgreSQL record
   */
  async applyCleaning(datasetId, config) {
    const res = await api.post(`/api/datasets/${datasetId}/clean`, {
      config,
    });
    return res.data;
  },

  /**
   * Get cleaning history for a dataset
   */
  async getDatasetCleanings(datasetId, skip = 0, limit = 50) {
    const res = await api.get(`/api/datasets/${datasetId}/cleanings`, {
      params: { skip, limit },
    });
    return res.data; // { total: int, items: [...] }
  },

  /**
   * Get cleaning record details by ID
   */
  async getCleaningRecord(cleaningId) {
    const res = await api.get(`/api/cleanings/${cleaningId}`);
    return res.data;
  },

  /**
   * Download cleaned CSV file attachment
   * Returns a Blob and triggers safe browser download
   */
  async downloadCleanedFile(cleaningId, fallbackFilename = 'cleaned_dataset.csv') {
    const res = await api.get(`/api/cleanings/${cleaningId}/download`, {
      params: { export_safe: true },
      responseType: 'blob',
    });

    // Extract filename from Content-Disposition header if available
    let filename = fallbackFilename;
    const disposition = res.headers['content-disposition'];
    if (disposition && disposition.indexOf('attachment') !== -1) {
      const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
      const matches = filenameRegex.exec(disposition);
      if (matches != null && matches[1]) {
        filename = matches[1].replace(/['"]/g, '');
      }
    }

    // Trigger browser file download
    const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8;' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
    return true;
  },
};
