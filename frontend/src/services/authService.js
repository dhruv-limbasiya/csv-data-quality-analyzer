import api from './api';

export const authService = {
  /**
   * Register a new account
   * Payload: { username, email, password }
   */
  async register(data) {
    const res = await api.post('/api/auth/register', data);
    return res.data;
  },

  /**
   * Log in user
   * Payload: { username_or_email, password }
   */
  async login(credentials) {
    const res = await api.post('/api/auth/login', credentials);
    return res.data;
  },

  /**
   * Log out user and clear cookies
   */
  async logout() {
    const res = await api.post('/api/auth/logout');
    return res.data;
  },

  /**
   * Get current authenticated user profile
   */
  async getProfile() {
    const res = await api.get('/api/auth/me');
    return res.data;
  },

  /**
   * Fetch/refresh CSRF token
   */
  async getCsrf() {
    const res = await api.get('/api/auth/csrf');
    return res.data;
  },
};
