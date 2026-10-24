import axios from 'axios';

/**
 * Reusable Axios HTTP client configured for the FastAPI backend.
 * - Supports HTTP-only cookie session authentication via withCredentials: true.
 * - Auto-attaches CSRF token from document.cookie into X-CSRF-Token header on state-changing requests.
 * - Safe error normalization.
 */

const API_BASE_URL = '';

const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true, // Send and receive session and csrf cookies
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * Extract a cookie by name from document.cookie
 */
export function getCookie(name) {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(new RegExp('(^|;\\s*)(' + name + ')=([^;]*)'));
  return match ? decodeURIComponent(match[3]) : null;
}

// Request Interceptor: Attach CSRF token on state-changing methods
api.interceptors.request.use(
  async (config) => {
    const method = config.method ? config.method.toUpperCase() : 'GET';
    const stateChanging = ['POST', 'PUT', 'DELETE', 'PATCH'];

    if (stateChanging.includes(method)) {
      let csrfToken = getCookie('csrf_token');
      // Proactively fetch CSRF token if missing on a state-changing operation (excluding public login/register)
      if (!csrfToken && !config.url?.includes('/api/auth/login') && !config.url?.includes('/api/auth/register')) {
        try {
          const csrfRes = await axios.get(`${API_BASE_URL}/api/auth/csrf`, { withCredentials: true });
          csrfToken = csrfRes.data?.csrf_token || getCookie('csrf_token');
        } catch {
          // If unauthenticated or network error, let request continue and backend respond
        }
      }

      if (csrfToken && !config.headers['X-CSRF-Token']) {
        config.headers['X-CSRF-Token'] = csrfToken;
      }
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response Interceptor: Safe error formatting
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // If response is a blob (e.g. failed file download returning JSON error as blob), parse it
    if (error.response?.data instanceof Blob && error.response.data.type?.includes('application/json')) {
      return new Promise((_, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
          try {
            const parsed = JSON.parse(reader.result);
            error.response.data = parsed;
            const detail = parsed?.detail;
            error.formattedMessage = typeof detail === 'string' ? detail : (error.message || 'File download failed.');
          } catch {
            error.formattedMessage = error.message || 'File download failed.';
          }
          reject(error);
        };
        reader.onerror = () => reject(error);
        reader.readAsText(error.response.data);
      });
    }

    // Standardize error message extraction
    const detail = error.response?.data?.detail;
    let message = 'An unexpected network error occurred.';
    if (error.response?.status >= 500) {
      message = 'The server could not complete your request. Please try again later.';
    } else if (typeof detail === 'string') {
      message = detail;
    } else if (Array.isArray(detail)) {
      message = detail.map((d) => (d.msg ? `${d.loc ? d.loc.join('.') + ': ' : ''}${d.msg}` : JSON.stringify(d))).join(', ');
    } else if (error.response?.status === 401) {
      message = 'Your session has expired or authentication is required. Please log in.';
    } else if (error.message) {
      message = error.message;
    }
    error.formattedMessage = message;
    return Promise.reject(error);
  }
);

export default api;
