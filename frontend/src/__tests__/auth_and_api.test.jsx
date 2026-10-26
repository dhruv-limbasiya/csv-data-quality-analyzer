import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import axios from 'axios';
import api, { getCookie } from '../services/api';
import { authService } from '../services/authService';
import { datasetService } from '../services/datasetService';
import { analysisService } from '../services/analysisService';
import { cleaningService } from '../services/cleaningService';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('Frontend API Client & Services', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('correctly parses cookies from document.cookie', () => {
    // Mock document.cookie
    Object.defineProperty(document, 'cookie', {
      writable: true,
      value: 'session_id=mock_session; csrf_token=mock_csrf_val_123',
    });

    expect(getCookie('session_id')).toBe('mock_session');
    expect(getCookie('csrf_token')).toBe('mock_csrf_val_123');
    expect(getCookie('nonexistent')).toBeNull();
  });

  it('uses the configured API origin and remains same-origin when unset', () => {
    expect(api.defaults.baseURL).toBe((import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, ''));
    expect(api.defaults.withCredentials).toBe(true);
  });

  it('fetches and attaches the CSRF token when the API cookie is cross-origin and host-only', async () => {
    Object.defineProperty(document, 'cookie', { writable: true, value: '' });
    const getSpy = vi.spyOn(axios, 'get').mockResolvedValue({
      data: { csrf_token: 'signed-csrf-token' },
    });
    const requestInterceptor = api.interceptors.request.handlers[0].fulfilled;
    const config = await requestInterceptor({
      method: 'post',
      url: '/api/datasets/8/analyze',
      headers: {},
    });

    expect(getSpy).toHaveBeenCalledWith(
      `${api.defaults.baseURL}/api/auth/csrf`,
      { withCredentials: true }
    );
    expect(config.headers['X-CSRF-Token']).toBe('signed-csrf-token');
  });

  it('normalizes FastAPI validation errors in response interceptor', async () => {
    const errorResponse = {
      response: {
        status: 422,
        data: {
          detail: [
            { loc: ['body', 'email'], msg: 'value is not a valid email address' },
          ],
        },
      },
    };

    // Trigger error interceptor
    const rejectedHandler = api.interceptors.response.handlers[0].rejected;
    await expect(rejectedHandler(errorResponse)).rejects.toHaveProperty(
      'formattedMessage',
      'body.email: value is not a valid email address'
    );
  });

  it('normalizes string error details', async () => {
    const errorResponse = {
      response: {
        status: 400,
        data: {
          detail: 'Invalid cleaning configuration provided.',
        },
      },
    };

    const rejectedHandler = api.interceptors.response.handlers[0].rejected;
    await expect(rejectedHandler(errorResponse)).rejects.toHaveProperty(
      'formattedMessage',
      'Invalid cleaning configuration provided.'
    );
  });

  it('handles 401 session expiration gracefully', async () => {
    const errorResponse = {
      response: {
        status: 401,
        data: {},
      },
    };

    const rejectedHandler = api.interceptors.response.handlers[0].rejected;
    await expect(rejectedHandler(errorResponse)).rejects.toHaveProperty(
      'formattedMessage',
      'Your session has expired or authentication is required. Please log in.'
    );
  });

  it('shows a safe message for server errors without exposing response details', async () => {
    const errorResponse = {
      message: 'Request failed with status code 500',
      response: {
        status: 500,
        data: { detail: 'Traceback: internal database error' },
      },
    };

    const rejectedHandler = api.interceptors.response.handlers[0].rejected;
    await expect(rejectedHandler(errorResponse)).rejects.toHaveProperty(
      'formattedMessage',
      'The server could not complete your request. Please try again later.'
    );
  });
});

describe('Frontend Service Endpoints', () => {
  it('calls authService endpoints with expected parameters', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({ data: { id: 1, username: 'testuser' } });
    const getSpy = vi.spyOn(api, 'get').mockResolvedValue({ data: { id: 1, username: 'testuser' } });

    await authService.login({ username_or_email: 'testuser', password: 'password123' });
    expect(postSpy).toHaveBeenCalledWith('/api/auth/login', { username_or_email: 'testuser', password: 'password123' });

    await authService.getProfile();
    expect(getSpy).toHaveBeenCalledWith('/api/auth/me');

    await authService.logout();
    expect(postSpy).toHaveBeenCalledWith('/api/auth/logout');
  });

  it('calls datasetService upload with FormData and onProgress', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({ data: { id: 10 } });
    const mockFile = new File(['a,b\n1,2'], 'test.csv', { type: 'text/csv' });

    await datasetService.uploadDataset(mockFile);
    expect(postSpy).toHaveBeenCalledWith(
      '/api/datasets/upload',
      expect.any(FormData),
      expect.objectContaining({
        headers: { 'Content-Type': 'multipart/form-data' },
      })
    );
  });

  it('calls analysisService and cleaningService endpoints', async () => {
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({ data: { id: 5 } });
    const getSpy = vi.spyOn(api, 'get').mockResolvedValue({ data: { items: [] } });

    await analysisService.runAnalysis(12);
    expect(postSpy).toHaveBeenCalledWith('/api/datasets/12/analyze');

    await cleaningService.previewCleaning(12, { whitespace_cleaning: { enabled: true } });
    expect(postSpy).toHaveBeenCalledWith(
      '/api/datasets/12/clean/preview',
      { config: { whitespace_cleaning: { enabled: true } }, preview_limit: 10 }
    );

    await cleaningService.getDatasetCleanings(12);
    expect(getSpy).toHaveBeenCalledWith('/api/datasets/12/cleanings', { params: { skip: 0, limit: 50 } });
  });

  it('requests formula-safe cleaned CSV downloads', async () => {
    const getSpy = vi.spyOn(api, 'get').mockResolvedValue({
      data: new Blob(['id,value\n1,safe']),
      headers: { 'content-disposition': 'attachment; filename="cleaned.csv"' },
    });
    const createObjectURL = vi.fn(() => 'blob:cleaned-csv');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    await expect(cleaningService.downloadCleanedFile(42)).resolves.toBe(true);

    expect(getSpy).toHaveBeenCalledWith('/api/cleanings/42/download', {
      params: { export_safe: true },
      responseType: 'blob',
    });
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:cleaned-csv');
  });
});
