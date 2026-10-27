import {
  DEMO_ANALYSIS,
  DEMO_CLEANING_RECORDS,
  DEMO_DATASETS,
} from '../utils/mockData';

const clone = (value) => JSON.parse(JSON.stringify(value));
const DEMO_USER_ID = 0;
const DEMO_ROWS = {
  1: [
    { id: 101, full_name: '  Ava Patel ', email: 'ava@example.com', age: 34, income: 82000, join_date: '2024-03-12', phone: '555-0101', status: 'active' },
    { id: 102, full_name: 'Noah Kim', email: 'noah@example.com', age: null, income: 76000, join_date: '2024-05-08', phone: null, status: 'active' },
    { id: 103, full_name: 'Mia Chen', email: 'invalid-email', age: 29, income: null, join_date: '2024-06-20', phone: '555-0103', status: 'inactive' },
    { id: 104, full_name: '  Ava Patel ', email: 'ava@example.com', age: 34, income: 82000, join_date: '2024-03-12', phone: '555-0101', status: 'active' },
  ],
  2: [
    { transaction_id: 'T-1001', customer_id: 101, product: 'Notebook', category: 'Office', quantity: 2, unit_price: 8.5, total_amount: 17, transaction_date: '2026-09-01', payment_method: 'Card', city: 'Boston', discount: 0, tax: 1.36, shipping: 3.5, returned: false },
    { transaction_id: 'T-1002', customer_id: 102, product: 'Desk lamp', category: 'Home', quantity: 1, unit_price: 32, total_amount: 32, transaction_date: '2026-09-03', payment_method: 'Wallet', city: 'Austin', discount: 2, tax: 2.4, shipping: 0, returned: false },
    { transaction_id: 'T-1003', customer_id: 103, product: 'Water bottle', category: 'Outdoor', quantity: 3, unit_price: 14, total_amount: null, transaction_date: '2026-09-04', payment_method: 'Card', city: 'Denver', discount: 0, tax: 3.36, shipping: 4, returned: false },
  ],
  3: [
    { employee_id: 'E-021', full_name: 'Jordan Lee', department: 'Engineering', location: 'Seattle', start_date: '2022-04-18', performance_rating: 4.2 },
    { employee_id: 'E-022', full_name: 'Sam Rivera', department: 'Operations', location: 'Chicago', start_date: '2023-01-09', performance_rating: 3.8 },
    { employee_id: 'E-023', full_name: 'Taylor Morgan', department: 'Design', location: 'Portland', start_date: '2021-11-02', performance_rating: 4.6 },
  ],
};

const COLUMN_NAMES = {
  1: ['id', 'full_name', 'email', 'age', 'income', 'join_date', 'phone', 'status'],
  2: ['transaction_id', 'customer_id', 'product', 'category', 'quantity', 'unit_price', 'total_amount', 'transaction_date', 'payment_method', 'city', 'discount', 'tax', 'shipping', 'returned'],
  3: ['employee_id', 'full_name', 'department', 'location', 'start_date', 'performance_rating'],
};

const datasets = DEMO_DATASETS.map((dataset) => ({
  ...clone(dataset),
  user_id: DEMO_USER_ID,
  original_filename: dataset.name,
  updated_at: dataset.created_at,
  is_cleaned_version: dataset.status === 'cleaned',
  columns_metadata: COLUMN_NAMES[dataset.id].map((name) => ({
    name,
    data_type: typeof DEMO_ROWS[dataset.id][0][name],
    sample_values: DEMO_ROWS[dataset.id].slice(0, 3).map((row) => row[name]),
  })),
}));

const analysis = {
  ...clone(DEMO_ANALYSIS),
  user_id: DEMO_USER_ID,
  created_at: '2026-10-24T15:00:00Z',
  summary_stats: {
    ...clone(DEMO_ANALYSIS.summary_stats),
    columns_quality: [
      { name: 'income', missing_percentage: 8.5 },
      { name: 'phone', missing_percentage: 6.2 },
      { name: 'age', missing_percentage: 2.1 },
      { name: 'email', missing_percentage: 0.8 },
    ],
  },
};

function getAnalysisForDataset(datasetId) {
  const dataset = getDatasetOrThrow(datasetId);
  const missingByDataset = {
    1: [
      { name: 'income', missing_percentage: 8.5 },
      { name: 'phone', missing_percentage: 6.2 },
      { name: 'age', missing_percentage: 2.1 },
      { name: 'email', missing_percentage: 0.8 },
    ],
    2: [{ name: 'total_amount', missing_percentage: 2.4 }],
    3: [],
  };
  const columns = COLUMN_NAMES[dataset.id];
  return {
    ...clone(analysis),
    id: 100 + dataset.id,
    dataset_id: dataset.id,
    overall_score: dataset.quality_score,
    summary_stats: {
      ...clone(analysis.summary_stats),
      total_rows: dataset.row_count,
      total_columns: dataset.column_count,
      total_cells: dataset.row_count * dataset.column_count,
      columns_quality: missingByDataset[dataset.id],
    },
    column_scores: Object.fromEntries(columns.map((column, index) => [
      column,
      dataset.id === 1 ? analysis.column_scores[column] : Math.max(70, 98 - index * 3),
    ])),
    issues: dataset.id === 1 ? clone(analysis.issues) : [],
    recommendations: dataset.id === 1
      ? clone(analysis.recommendations)
      : ['Review the sample missing-value distribution and inspect the selected columns.'],
  };
}

let nextCleaningId = 600;
const cleaningRecords = DEMO_CLEANING_RECORDS.map((record, index) => ({
  ...clone(record),
  dataset_id: index + 1,
  user_id: DEMO_USER_ID,
  status: 'demo-only',
  cleaning_summary: {
    operations_applied: [{ description: record.operations_summary }],
  },
  cleaning_config: {},
  output_file_size_bytes: 42000,
  output_column_count: datasets[index].column_count,
}));
const cleanedRowsById = new Map();

function getDatasetOrThrow(datasetId) {
  const dataset = datasets.find((item) => item.id === Number(datasetId));
  if (!dataset) {
    throw new Error('That sample dataset is not available in the public demo.');
  }
  return dataset;
}

function countMissing(rows) {
  return rows.reduce(
    (total, row) => total + Object.values(row).filter((value) => value == null || value === '').length,
    0
  );
}

function duplicateCount(rows) {
  return rows.length - new Set(rows.map((row) => JSON.stringify(row))).size;
}

function transformRows(datasetId, config) {
  getDatasetOrThrow(datasetId);
  const original = clone(DEMO_ROWS[datasetId]);
  const rows = clone(original);
  const operations = [];

  if (config.type_conversions?.length || config.outlier_handling?.enabled) {
    throw new Error('Type conversion and outlier processing are not enabled in the browser-only public demo.');
  }

  if (config.whitespace_cleaning?.enabled) {
    const options = config.whitespace_cleaning;
    let changes = 0;
    for (const row of rows) {
      for (const column of options.columns?.length ? options.columns : Object.keys(row)) {
        if (typeof row[column] !== 'string') continue;
        let value = row[column];
        if (options.trim_whitespace !== false) value = value.trim();
        if (options.collapse_internal_whitespace) value = value.replace(/\s+/g, ' ');
        if (value !== row[column]) changes += 1;
        row[column] = value;
      }
    }
    operations.push({ operation: 'whitespace_cleaning', description: 'Trimmed or normalized sample text whitespace.', changes_count: changes });
  }

  if (config.text_normalization?.enabled) {
    const options = config.text_normalization;
    let changes = 0;
    for (const row of rows) {
      for (const column of options.columns?.length ? options.columns : Object.keys(row)) {
        if (typeof row[column] !== 'string') continue;
        let value = row[column];
        if (options.standardize_null_markers && ['N/A', 'NULL', 'null', 'none', 'None', 'n/a', 'NA', '-', 'NaN'].includes(value.trim())) {
          value = null;
        } else if (options.case === 'lowercase') {
          value = value.toLowerCase();
        } else if (options.case === 'uppercase') {
          value = value.toUpperCase();
        }
        if (value !== row[column]) changes += 1;
        row[column] = value;
      }
    }
    operations.push({ operation: 'text_normalization', description: 'Normalized sample text values.', changes_count: changes });
  }

  const missing = config.missing_values;
  if (missing?.enabled) {
    if (missing.strategy === 'drop_rows') {
      const before = rows.length;
      for (let index = rows.length - 1; index >= 0; index -= 1) {
        const columns = missing.columns?.length ? missing.columns : Object.keys(rows[index]);
        if (columns.some((column) => rows[index][column] == null || rows[index][column] === '')) rows.splice(index, 1);
      }
      operations.push({ operation: 'missing_values', description: 'Dropped sample rows containing missing values.', changes_count: before - rows.length });
    } else if (missing.strategy === 'fill_constant') {
      const columns = missing.columns?.length ? missing.columns : Object.keys(rows[0] || {});
      let changes = 0;
      for (const row of rows) {
        for (const column of columns) {
          if (row[column] == null || row[column] === '') {
            row[column] = missing.fill_value;
            changes += 1;
          }
        }
      }
      operations.push({ operation: 'missing_values', description: 'Filled missing sample cells with the selected constant.', changes_count: changes });
    } else if (missing.strategy === 'drop_columns') {
      const columns = missing.columns || [];
      if (columns.length >= Object.keys(rows[0] || {}).length) {
        throw new Error('The public demo keeps at least one sample column.');
      }
      for (const row of rows) columns.forEach((column) => delete row[column]);
      operations.push({ operation: 'missing_values', description: 'Dropped selected sample columns.', changes_count: columns.length });
    } else if (['fill_mean', 'fill_median', 'fill_mode'].includes(missing.strategy)) {
      const columns = missing.columns || [];
      let changes = 0;
      for (const column of columns) {
        const values = rows.map((row) => row[column]).filter((value) => value != null && value !== '');
        if (!values.length) continue;
        let fillValue;
        if (missing.strategy === 'fill_mode') {
          const counts = new Map();
          values.forEach((value) => counts.set(value, (counts.get(value) || 0) + 1));
          fillValue = [...counts.entries()].sort((left, right) => right[1] - left[1])[0][0];
        } else {
          const numbers = values.map(Number).filter(Number.isFinite).sort((a, b) => a - b);
          if (!numbers.length) {
            throw new Error(`The public demo cannot calculate a numeric fill for "${column}".`);
          }
          fillValue = missing.strategy === 'fill_mean'
            ? numbers.reduce((sum, value) => sum + value, 0) / numbers.length
            : numbers[Math.floor((numbers.length - 1) / 2)];
        }
        for (const row of rows) {
          if (row[column] == null || row[column] === '') {
            row[column] = fillValue;
            changes += 1;
          }
        }
      }
      operations.push({ operation: 'missing_values', description: 'Filled missing sample cells using the selected strategy.', changes_count: changes });
    } else if (missing.strategy !== 'keep') {
      throw new Error('This missing-value strategy is not simulated in the browser-only public demo.');
    }
  }

  if (config.duplicate_removal?.enabled) {
    const before = rows.length;
    const keyFor = (row) => JSON.stringify(config.duplicate_removal.subset_columns?.length
      ? Object.fromEntries(config.duplicate_removal.subset_columns.map((column) => [column, row[column]]))
      : row);
    const source = config.duplicate_removal.keep === 'last' ? [...rows].reverse() : rows;
    const seen = new Set();
    const uniqueRows = source.filter((row) => {
      const key = keyFor(row);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
    if (config.duplicate_removal.keep === 'last') uniqueRows.reverse();
    rows.splice(0, rows.length, ...uniqueRows);
    operations.push({ operation: 'duplicate_removal', description: 'Removed duplicate sample rows.', changes_count: before - rows.length });
  }

  const summary = {
    rows: { before: original.length, after: rows.length, difference: rows.length - original.length },
    columns: {
      before: Object.keys(original[0] || {}).length,
      after: Object.keys(rows[0] || {}).length,
      difference: Object.keys(rows[0] || {}).length - Object.keys(original[0] || {}).length,
    },
    missing_cells: { before: countMissing(original), after: countMissing(rows), difference: countMissing(rows) - countMissing(original) },
    duplicate_rows: { before: duplicateCount(original), after: duplicateCount(rows), difference: duplicateCount(rows) - duplicateCount(original) },
    operations_applied: operations,
    warnings: [],
    skipped_operations: [],
    configuration_used: clone(config),
  };
  return { original, rows, summary };
}

function createCleaningRecord(datasetId, config) {
  const result = transformRows(datasetId, config);
  if (!result.rows.length || !Object.keys(result.rows[0]).length) {
    throw new Error('Public demo cleaning must leave at least one sample row and one sample column.');
  }
  const id = nextCleaningId++;
  const dataset = getDatasetOrThrow(datasetId);
  const record = {
    id,
    dataset_id: dataset.id,
    user_id: DEMO_USER_ID,
    datasetName: dataset.original_filename,
    status: 'demo-only',
    output_filename: `demo_cleaned_${dataset.original_filename}`,
    output_row_count: result.rows.length,
    output_column_count: Object.keys(result.rows[0] || {}).length,
    output_file_size_bytes: 0,
    created_at: new Date().toISOString(),
    cleaning_summary: result.summary,
    cleaning_config: clone(config),
    demo_only: true,
  };
  cleaningRecords.unshift(record);
  cleanedRowsById.set(id, result.rows);
  return { record: clone(record), result };
}

function downloadCsv(filename, rows) {
  if (!rows?.length) throw new Error('No sample output is available to download.');
  const columns = Object.keys(rows[0]);
  const csv = [
    columns.join(','),
    ...rows.map((row) => columns.map((column) => {
    let value = row[column] == null ? '' : String(row[column]);
    if (/^[=+\-@\t\r]/.test(value)) value = `'${value}`;
    return `"${value.replaceAll('"', '""')}"`;
    }).join(',')),
  ].join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  return true;
}

export const publicDemoService = {
  async listDatasets() {
    return { total: datasets.length, items: clone(datasets) };
  },

  async getDataset(datasetId) {
    const dataset = getDatasetOrThrow(datasetId);
    return { ...clone(dataset), preview_rows: clone(DEMO_ROWS[dataset.id]) };
  },

  async uploadDataset() {
    throw new Error('CSV uploads are disabled in the public demo. Use one of the synthetic sample datasets instead.');
  },

  async runAnalysis(datasetId) {
    return getAnalysisForDataset(datasetId);
  },

  async getDatasetAnalyses(datasetId) {
    return { total: 1, items: [getAnalysisForDataset(datasetId)] };
  },

  async getAnalysis(analysisId) {
    const datasetId = Number(analysisId) - 100;
    return getAnalysisForDataset(datasetId);
  },

  async previewCleaning(datasetId, config, previewLimit = 10) {
    getDatasetOrThrow(datasetId);
    const result = transformRows(Number(datasetId), config);
    return {
      dataset_id: Number(datasetId),
      summary: result.summary,
      original_preview: result.original.slice(0, previewLimit),
      cleaned_preview: result.rows.slice(0, previewLimit),
      columns: Object.keys(result.rows[0] || {}),
      demo_only: true,
    };
  },

  async applyCleaning(datasetId, config) {
    return createCleaningRecord(Number(datasetId), config).record;
  },

  async getDatasetCleanings(datasetId, skip = 0, limit = 50) {
    getDatasetOrThrow(datasetId);
    const items = cleaningRecords.filter((record) => record.dataset_id === Number(datasetId));
    return { total: items.length, items: clone(items.slice(skip, skip + limit)) };
  },

  async getCleaningRecord(cleaningId) {
    const record = cleaningRecords.find((item) => item.id === Number(cleaningId));
    if (!record) throw new Error('That sample cleaning record is not available in the public demo.');
    return clone(record);
  },

  async downloadCleanedFile(cleaningId, fallbackFilename = 'demo_cleaned_dataset.csv') {
    const record = cleaningRecords.find((item) => item.id === Number(cleaningId));
    if (!record) throw new Error('That sample cleaning record is not available in the public demo.');
    return downloadCsv(
      record.output_filename || fallbackFilename,
      cleanedRowsById.get(record.id) || DEMO_ROWS[record.dataset_id]
    );
  },
};
