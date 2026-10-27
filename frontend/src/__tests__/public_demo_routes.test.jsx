import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { useAuthMock } = vi.hoisted(() => ({ useAuthMock: vi.fn() }));

vi.mock('../context/AuthContext', () => ({
  useAuth: useAuthMock,
}));

import { ProtectedRoute } from '../components/layout/RouteGuards';

describe('Protected routes in public demo mode', () => {
  let container;
  let root;

  beforeEach(() => {
    useAuthMock.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      isDemoMode: false,
      isPublicDemo: true,
      authError: false,
    });
    container = document.createElement('div');
    root = createRoot(container);
  });

  it('allows direct navigation to a protected application page without a login', async () => {
    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={['/datasets']}>
          <Routes>
            <Route
              path="/datasets"
              element={<ProtectedRoute><p>Sample datasets visible</p></ProtectedRoute>}
            />
            <Route path="/login" element={<p>Login page</p>} />
          </Routes>
        </MemoryRouter>
      );
    });

    expect(container.textContent).toContain('Sample datasets visible');
    expect(container.textContent).not.toContain('Login page');
    await act(async () => root.unmount());
  });
});
