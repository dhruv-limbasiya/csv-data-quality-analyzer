import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { loginMock, startDemoMock, useAuthMock } = vi.hoisted(() => ({
  loginMock: vi.fn(),
  startDemoMock: vi.fn(),
  useAuthMock: vi.fn(),
}));

vi.mock('../context/AuthContext', () => ({
  useAuth: useAuthMock,
}));

import LoginPage from '../pages/LoginPage';

describe('LoginPage demo access', () => {
  let container;
  let root;

  beforeEach(() => {
    loginMock.mockReset();
    startDemoMock.mockReset();
    useAuthMock.mockReturnValue({
      login: loginMock,
      startDemo: startDemoMock,
      isDemoMode: true,
    });
    container = document.createElement('div');
    root = createRoot(container);
  });

  it('offers demo access without displaying regular login or registration forms', async () => {
    await act(async () => {
      root.render(
        <MemoryRouter>
          <LoginPage />
        </MemoryRouter>
      );
    });

    expect(container.textContent).toContain('Enter Demo');
    expect(container.textContent).not.toContain('Sign In');
    expect(container.textContent).not.toContain('Register here');

    await act(async () => {
      container.querySelector('button').click();
    });

    expect(startDemoMock).toHaveBeenCalledOnce();
    await act(async () => root.unmount());
  });

  it('preserves the regular login form when demo mode is disabled', async () => {
    useAuthMock.mockReturnValue({
      login: loginMock,
      startDemo: startDemoMock,
      isDemoMode: false,
    });

    await act(async () => {
      root.render(
        <MemoryRouter>
          <LoginPage />
        </MemoryRouter>
      );
    });

    expect(container.textContent).toContain('Sign In');
    expect(container.textContent).toContain('Register here');
    expect(container.textContent).not.toContain('Enter Demo');
    await act(async () => root.unmount());
  });

  it('shows a safe error when demo session creation fails', async () => {
    startDemoMock.mockRejectedValue({
      formattedMessage: 'Demo API is unavailable.',
    });

    await act(async () => {
      root.render(
        <MemoryRouter>
          <LoginPage />
        </MemoryRouter>
      );
    });

    await act(async () => {
      container.querySelector('button').click();
    });

    expect(container.textContent).toContain('Demo API is unavailable.');
    await act(async () => root.unmount());
  });
});
