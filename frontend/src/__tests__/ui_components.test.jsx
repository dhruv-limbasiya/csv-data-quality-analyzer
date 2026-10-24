import { describe, it, expect } from 'vitest';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Card, Badge, PageHeader, EmptyState, FormField } from '../components/common/UI';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

describe('UI Common Components', () => {
  it('renders Badge with variants correctly', async () => {
    const container = document.createElement('div');
    const root = createRoot(container);
    await act(async () => {
      root.render(React.createElement(Badge, { variant: 'success' }, 'Completed'));
    });
    expect(container.textContent).toContain('Completed');
    expect(container.firstChild.className).toContain('emerald');

    await act(async () => {
      root.render(React.createElement(Badge, { variant: 'danger' }, 'Error'));
    });
    expect(container.textContent).toContain('Error');
    expect(container.firstChild.className).toContain('rose');
  });

  it('renders Card with title and subtitle', async () => {
    const container = document.createElement('div');
    const root = createRoot(container);
    await act(async () => {
      root.render(
        React.createElement(
          Card,
          { title: 'Quality Metrics', subtitle: 'Calculated from 1000 cells' },
          React.createElement('p', null, 'Card Content')
        )
      );
    });
    expect(container.textContent).toContain('Quality Metrics');
    expect(container.textContent).toContain('Calculated from 1000 cells');
    expect(container.textContent).toContain('Card Content');
  });

  it('renders PageHeader with actions', async () => {
    const container = document.createElement('div');
    const root = createRoot(container);
    await act(async () => {
      root.render(
        React.createElement(PageHeader, {
          title: 'Datasets',
          description: 'Upload and manage files',
          actions: React.createElement('button', null, 'Action Button'),
        })
      );
    });
    expect(container.textContent).toContain('Datasets');
    expect(container.textContent).toContain('Upload and manage files');
    expect(container.textContent).toContain('Action Button');
  });

  it('renders FormField with label and required star', async () => {
    const container = document.createElement('div');
    const root = createRoot(container);
    await act(async () => {
      root.render(
        React.createElement(
          FormField,
          { label: 'Username', id: 'uname', required: true },
          React.createElement('input', { id: 'uname' })
        )
      );
    });
    expect(container.textContent).toContain('Username');
    expect(container.textContent).toContain('*');
  });

  it('renders EmptyState with call-to-action button', async () => {
    const container = document.createElement('div');
    const root = createRoot(container);
    await act(async () => {
      root.render(
        React.createElement(EmptyState, {
          title: 'No Datasets Found',
          description: 'Upload your first CSV file to begin.',
          action: React.createElement('button', null, 'Upload CSV'),
        })
      );
    });
    expect(container.textContent).toContain('No Datasets Found');
    expect(container.textContent).toContain('Upload your first CSV file to begin.');
    expect(container.textContent).toContain('Upload CSV');
  });
});
