/**
 * Isolated demo datasets for Phase 6 visual layout presentation.
 * Will be cleanly swapped for dynamic backend API queries in Phase 7.
 */

export const DEMO_DATASETS = [
  {
    id: 1,
    name: 'customers_q3_raw.csv',
    row_count: 1250,
    column_count: 8,
    file_size_bytes: 98450,
    created_at: '2026-10-24T14:30:00Z',
    quality_score: 84.5,
    status: 'analyzed',
  },
  {
    id: 2,
    name: 'ecommerce_transactions_2026.csv',
    row_count: 4800,
    column_count: 14,
    file_size_bytes: 420100,
    created_at: '2026-10-24T12:15:00Z',
    quality_score: 62.0,
    status: 'analyzed',
  },
  {
    id: 3,
    name: 'employee_roster_clean.csv',
    row_count: 350,
    column_count: 6,
    file_size_bytes: 28400,
    created_at: '2026-10-23T18:00:00Z',
    quality_score: 96.0,
    status: 'cleaned',
  },
];

export const DEMO_ANALYSIS = {
  id: 101,
  dataset_id: 1,
  dataset_name: 'customers_q3_raw.csv',
  overall_score: 84.5,
  summary_stats: {
    total_rows: 1250,
    total_columns: 8,
    total_cells: 10000,
    total_missing_cells: 145,
    columns_with_missing: 3,
    duplicate_rows: 18,
    duplicate_rows_percentage: 1.44,
    total_invalid_values: 32,
    score_breakdown: {
      missing_penalty: 5.08,
      duplicate_penalty: 0.36,
      validity_penalty: 9.6,
      consistency_penalty: 0.0,
      formula: '100.0 - missing_pen - dup_pen - val_pen - const_pen',
      explanation: 'Composite health based on cell completeness, row uniqueness, format validity, and variance consistency.',
    },
  },
  column_scores: {
    id: 100.0,
    full_name: 98.4,
    email: 88.0,
    age: 94.5,
    income: 82.0,
    join_date: 91.0,
    phone: 72.5,
    status: 100.0,
  },
  missing_distribution: [
    { name: 'income', missingPct: 8.5 },
    { name: 'phone', missingPct: 6.2 },
    { name: 'age', missingPct: 2.1 },
    { name: 'email', missingPct: 0.8 },
  ],
  issues: [
    {
      severity: 'error',
      category: 'invalid_format',
      column: 'email',
      count: 14,
      description: "Found 14 invalid email formats in column 'email'.",
      rule_applied: 'Standard RFC 5322 compliant regex matching.',
    },
    {
      severity: 'warning',
      category: 'missing_values',
      column: 'income',
      count: 106,
      description: "Column 'income' has 8.5% missing records.",
      rule_applied: 'Missing value ratio threshold.',
    },
    {
      severity: 'warning',
      category: 'duplicates',
      column: null,
      count: 18,
      description: 'Found 18 duplicate rows across all columns.',
      rule_applied: 'Row-level duplicate hashing.',
    },
    {
      severity: 'info',
      category: 'whitespace_cells',
      column: 'full_name',
      count: 20,
      description: 'Found 20 whitespace-only cells in full_name.',
      rule_applied: 'String whitespace regex matching.',
    },
  ],
  recommendations: [
    "Address missing values in column 'income' using median imputation.",
    "Remove 18 duplicate rows to ensure uniqueness.",
    "Correct 14 malformed email addresses in 'email'.",
    "Trim and standardize whitespace in column 'full_name'.",
  ],
};

export const DEMO_CLEANING_RECORDS = [
  {
    id: 501,
    dataset_name: 'customers_q3_raw.csv',
    status: 'completed',
    created_at: '2026-10-24T16:00:00Z',
    output_filename: 'cleaned_customers_q3.csv',
    output_row_count: 1232,
    output_column_count: 8,
    operations_summary: 'Trimmed whitespace, imputed missing income with median, removed 18 duplicates.',
  },
  {
    id: 502,
    dataset_name: 'ecommerce_transactions_2026.csv',
    status: 'completed',
    created_at: '2026-10-24T15:20:00Z',
    output_filename: 'cleaned_ecommerce_2026.csv',
    output_row_count: 4760,
    output_column_count: 14,
    operations_summary: 'Removed 40 duplicates, converted transaction_date to datetime, clipped outliers in total_amount.',
  },
];
