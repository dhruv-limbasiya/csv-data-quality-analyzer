import React, { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Sparkles,
  Eye,
  CheckCircle2,
  AlertCircle,
  FileSpreadsheet,
} from 'lucide-react';
import { Card, Button, Badge, PageHeader, FormField } from '../components/common/UI';
import { datasetService } from '../services/datasetService';
import { cleaningService } from '../services/cleaningService';
import { useAuth } from '../context/AuthContext';

export default function CleaningPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { isPublicDemo } = useAuth();

  const [datasets, setDatasets] = useState([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState(
    location.state?.selectedDatasetId?.toString() || ''
  );

  // Cleaning options state
  const [whitespaceTrim, setWhitespaceTrim] = useState(true);
  const [collapseSpaces, setCollapseSpaces] = useState(false);

  const [textNormalization, setTextNormalization] = useState(false);
  const [textCase, setTextCase] = useState('lowercase');
  const [nullMarkers, setNullMarkers] = useState(true);

  const [missingStrategy, setMissingStrategy] = useState('keep');
  const [missingTargetColumn, setMissingTargetColumn] = useState('');
  const [missingFillValue, setMissingFillValue] = useState('');

  const [dedupEnabled, setDedupEnabled] = useState(true);
  const [dedupKeep, setDedupKeep] = useState('first');

  const [outlierHandling, setOutlierHandling] = useState(false);
  const [outlierColumn, setOutlierColumn] = useState('');
  const [outlierTreatment, setOutlierTreatment] = useState('clip');

  // Preview & execution state
  const [previewResult, setPreviewResult] = useState(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [error, setError] = useState(null);
  const [successRecord, setSuccessRecord] = useState(null);
  const [showApplyConfirm, setShowApplyConfirm] = useState(false);

  // Load available datasets
  useEffect(() => {
    async function loadDatasets() {
      try {
        const data = await datasetService.listDatasets();
        const items = data.items || [];
        setDatasets(items);
        if (!selectedDatasetId && items.length > 0) {
          setSelectedDatasetId(items[0].id.toString());
        }
      } catch (err) {
        setError(err.formattedMessage || 'Failed to load datasets.');
      }
    }
    loadDatasets();
  }, []);

  const selectedDataset = datasets.find((d) => d.id.toString() === selectedDatasetId.toString());
  const columnsList = selectedDataset?.columns_metadata?.map((c) => c.name) || [];

  // Set default target columns when dataset changes
  useEffect(() => {
    if (columnsList.length > 0) {
      if (!missingTargetColumn) setMissingTargetColumn(columnsList[0]);
      if (!outlierColumn) setOutlierColumn(columnsList[0]);
    }
  }, [columnsList]);

  // Construct valid CleaningConfig matching backend schema
  const buildCleaningConfig = () => {
    const config = {};

    if (whitespaceTrim || collapseSpaces) {
      config.whitespace_cleaning = {
        enabled: true,
        trim_whitespace: whitespaceTrim,
        collapse_internal_whitespace: collapseSpaces,
      };
    }

    if (textNormalization) {
      config.text_normalization = {
        enabled: true,
        case: textCase === 'none' ? null : textCase,
        normalize_spaces: false,
        standardize_null_markers: nullMarkers,
      };
    }

    if (missingStrategy !== 'keep') {
      const mc = {
        enabled: true,
        strategy: missingStrategy,
      };
      if (['fill_mean', 'fill_median', 'fill_mode', 'drop_columns'].includes(missingStrategy)) {
        mc.columns = missingTargetColumn ? [missingTargetColumn] : [];
      } else if (missingStrategy === 'fill_constant') {
        mc.columns = missingTargetColumn ? [missingTargetColumn] : [];
        mc.fill_value = missingFillValue;
      }
      config.missing_values = mc;
    }

    if (dedupEnabled) {
      config.duplicate_removal = {
        enabled: true,
        keep: dedupKeep,
      };
    }

    if (outlierHandling && outlierColumn) {
      config.outlier_handling = {
        enabled: true,
        columns: [outlierColumn],
        method: 'iqr',
        iqr_multiplier: 1.5,
        treatment: outlierTreatment,
      };
    }

    return config;
  };

  // 1. Submit preview request
  const handlePreview = async () => {
    if (!selectedDatasetId) {
      setError('Please select a dataset to clean.');
      return;
    }
    setIsPreviewLoading(true);
    setError(null);
    setSuccessRecord(null);

    const config = buildCleaningConfig();
    try {
      const preview = await cleaningService.previewCleaning(selectedDatasetId, config, 10);
      setPreviewResult(preview);
    } catch (err) {
      setError(err.formattedMessage || 'Preview request failed.');
    } finally {
      setIsPreviewLoading(false);
    }
  };

  // 2. Submit apply cleaning request
  const handleApply = async () => {
    if (!selectedDatasetId) return;
    setIsApplying(true);
    setError(null);
    setShowApplyConfirm(false);

    const config = buildCleaningConfig();
    try {
      const record = await cleaningService.applyCleaning(selectedDatasetId, config);
      setSuccessRecord(record);
      setPreviewResult(null);
    } catch (err) {
      setError(err.formattedMessage || 'Failed to apply cleaning operations.');
    } finally {
      setIsApplying(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Data Cleaning Studio"
        description={isPublicDemo
          ? 'Try supported transformations on fictional sample rows. Results are browser-only and are discarded when this page reloads.'
          : 'Configure deterministic transformations including missing imputation, deduplication, whitespace trimming, and outlier handling.'}
        actions={
          <div className="flex items-center gap-2.5">
            <Button
              variant="outline"
              icon={Eye}
              onClick={handlePreview}
              isLoading={isPreviewLoading}
              disabled={!selectedDatasetId || isPreviewLoading || isApplying}
            >
              Preview Changes
            </Button>
            <Button
              variant="primary"
              icon={Sparkles}
              onClick={() => setShowApplyConfirm(true)}
              disabled={!selectedDatasetId || isPreviewLoading || isApplying}
            >
              {isPublicDemo ? 'Apply Sample Cleaning' : 'Apply Cleaning'}
            </Button>
          </div>
        }
      />

      {/* Dataset Selection Header */}
      <Card className="p-4 bg-slate-900 text-white border-slate-800">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <FileSpreadsheet className="w-5 h-5 text-brand-400 shrink-0" />
            <div>
              <span className="text-xs text-slate-400 font-medium">Dataset to Clean:</span>
              <div className="mt-0.5">
                <select
                  value={selectedDatasetId}
                  onChange={(e) => {
                    setSelectedDatasetId(e.target.value);
                    setPreviewResult(null);
                    setSuccessRecord(null);
                  }}
                  className="bg-slate-800 border border-slate-700 text-white text-sm font-semibold rounded-lg px-3 py-1.5 focus:outline-hidden focus:ring-2 focus:ring-brand-500"
                >
                  {datasets.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.original_filename} ({d.row_count != null ? d.row_count.toLocaleString() : '?'} rows)
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
          <p className="text-xs text-slate-400">
            Note: Cleaning generates a <span className="text-slate-200 font-semibold">new version</span>. The original CSV remains intact.
          </p>
        </div>
      </Card>

      {/* Feedback Banners */}
      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-700 text-xs flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
          <Button variant="ghost" size="sm" onClick={() => setError(null)}>
            Dismiss
          </Button>
        </div>
      )}

      {successRecord && (
        <div className="p-5 bg-emerald-50 border border-emerald-200 rounded-xl space-y-3">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-2 text-emerald-800 font-semibold text-sm">
              <CheckCircle2 className="w-5 h-5 text-emerald-600" />
              <span>
                {isPublicDemo
                  ? 'Sample cleaning complete (browser-only; not saved)'
                  : 'Cleaning Completed & Persisted Successfully!'}
              </span>
            </div>
            <Badge variant="success">Job #{successRecord.id}</Badge>
          </div>
          <p className="text-xs text-emerald-700">
            {isPublicDemo ? 'Generated sample output ' : 'Saved as separate file '}
            <code className="font-mono">{successRecord.output_filename}</code> with{' '}
            <strong>{successRecord.output_row_count} rows</strong> and{' '}
            <strong>{successRecord.output_column_count} columns</strong>.
          </p>
          <div className="flex gap-2.5 pt-1">
            <Button
              variant="primary"
              size="sm"
              onClick={() => navigate('/cleaning-history')}
            >
              View in Cleaning History
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => cleaningService.downloadCleanedFile(successRecord.id, `${selectedDataset?.original_filename || 'dataset'}_cleaned.csv`)}
            >
              {isPublicDemo ? 'Download Sample CSV' : 'Download Cleaned CSV'}
            </Button>
          </div>
        </div>
      )}

      {/* Cleaning Configuration Panels */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Panel 1: Whitespace & Text Normalization */}
        <Card
          title="Whitespace & Text Normalization"
          subtitle="Sanitize character padding, repeated spaces, and textual missing markers"
        >
          <div className="space-y-4">
            <div className="p-3 bg-slate-50 rounded-lg flex items-start gap-3">
              <input
                type="checkbox"
                id="ws-trim"
                checked={whitespaceTrim}
                onChange={(e) => setWhitespaceTrim(e.target.checked)}
                className="mt-1 h-4 w-4 rounded-sm text-brand-600 focus:ring-brand-500 border-slate-300"
              />
              <label htmlFor="ws-trim" className="text-xs text-slate-700 cursor-pointer">
                <span className="font-semibold block text-slate-900">Trim Whitespace</span>
                Strip leading and trailing spaces from all text columns.
              </label>
            </div>

            <div className="p-3 bg-slate-50 rounded-lg flex items-start gap-3">
              <input
                type="checkbox"
                id="ws-collapse"
                checked={collapseSpaces}
                onChange={(e) => setCollapseSpaces(e.target.checked)}
                className="mt-1 h-4 w-4 rounded-sm text-brand-600 focus:ring-brand-500 border-slate-300"
              />
              <label htmlFor="ws-collapse" className="text-xs text-slate-700 cursor-pointer">
                <span className="font-semibold block text-slate-900">Collapse Internal Spaces</span>
                Replace multiple consecutive internal spaces with a single space.
              </label>
            </div>

            <div className="p-3 bg-slate-50 rounded-lg flex items-start gap-3">
              <input
                type="checkbox"
                id="text-norm"
                checked={textNormalization}
                onChange={(e) => setTextNormalization(e.target.checked)}
                className="mt-1 h-4 w-4 rounded-sm text-brand-600 focus:ring-brand-500 border-slate-300"
              />
              <label htmlFor="text-norm" className="text-xs text-slate-700 cursor-pointer">
                <span className="font-semibold block text-slate-900">Text Normalization & Missing Markers</span>
                Standardize case and convert textual placeholders ('N/A', 'NULL', 'None') to true empty cells.
              </label>
            </div>

            {textNormalization && (
              <div className="pt-2 pl-7 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-700">Casing:</span>
                  <select
                    value={textCase}
                    onChange={(e) => setTextCase(e.target.value)}
                    className="px-2.5 py-1.5 bg-slate-50 border border-slate-200 rounded-md text-xs font-medium"
                  >
                    <option value="none">Preserve Original Case</option>
                    <option value="lowercase">Convert to lowercase</option>
                    <option value="uppercase">Convert to UPPERCASE</option>
                  </select>
                </div>
                <div className="flex items-center gap-2 pt-1">
                  <input
                    type="checkbox"
                    id="null-markers"
                    checked={nullMarkers}
                    onChange={(e) => setNullMarkers(e.target.checked)}
                    className="h-3.5 w-3.5 rounded-sm text-brand-600 focus:ring-brand-500 border-slate-300"
                  />
                  <label htmlFor="null-markers" className="text-xs text-slate-700 cursor-pointer">
                    Convert 'N/A', 'NULL', 'None' to true empty cells
                  </label>
                </div>
              </div>
            )}
          </div>
        </Card>

        {/* Panel 2: Missing Values Remediator */}
        <Card
          title="Missing Value Remediation"
          subtitle="Resolve null cells via imputation, constants, or row dropping"
        >
          <div className="space-y-4">
            <FormField label="Remediation Strategy" id="missing-strategy">
              <select
                id="missing-strategy"
                value={missingStrategy}
                onChange={(e) => setMissingStrategy(e.target.value)}
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-xs font-medium text-slate-800"
              >
                <option value="keep">Keep missing values unchanged</option>
                <option value="fill_median">Fill numerical column with Median</option>
                <option value="fill_mean">Fill numerical column with Mean</option>
                <option value="fill_mode">Fill categorical column with Mode (Most Frequent)</option>
                <option value="fill_constant">Fill selected column with Constant Value</option>
                <option value="drop_rows">Drop rows containing missing values</option>
              </select>
            </FormField>

            {['fill_median', 'fill_mean', 'fill_mode', 'fill_constant'].includes(missingStrategy) && (
              <FormField label="Target Column" id="target-col">
                <select
                  id="target-col"
                  value={missingTargetColumn}
                  onChange={(e) => setMissingTargetColumn(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-xs font-medium text-slate-800"
                >
                  {columnsList.map((col) => (
                    <option key={col} value={col}>
                      {col}
                    </option>
                  ))}
                </select>
              </FormField>
            )}

            {missingStrategy === 'fill_constant' && (
              <FormField label="Constant Fill Value" id="fill-val">
                <input
                  type="text"
                  id="fill-val"
                  value={missingFillValue}
                  onChange={(e) => setMissingFillValue(e.target.value)}
                  placeholder="e.g. Unknown or 0"
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-xs"
                />
              </FormField>
            )}

            <div className="p-3 bg-slate-50 rounded-lg text-xs text-slate-500">
              <span className="font-semibold text-slate-700">Safety Policy: </span>
              Safety checks will reject operations that would drop 100% of rows or all columns.
            </div>
          </div>
        </Card>

        {/* Panel 3: Duplicate-Row Removal */}
        <Card
          title="Duplicate-Row Removal"
          subtitle="Deduplicate records based on full rows or unique primary keys"
        >
          <div className="space-y-4">
            <div className="p-3 bg-slate-50 rounded-lg flex items-start gap-3">
              <input
                type="checkbox"
                id="dedup-check"
                checked={dedupEnabled}
                onChange={(e) => setDedupEnabled(e.target.checked)}
                className="mt-1 h-4 w-4 rounded-sm text-brand-600 focus:ring-brand-500 border-slate-300"
              />
              <label htmlFor="dedup-check" className="text-xs text-slate-700 cursor-pointer">
                <span className="font-semibold block text-slate-900">Enable Deduplication</span>
                Identify and drop subsequent occurrences of duplicated entries.
              </label>
            </div>

            {dedupEnabled && (
              <div className="space-y-3 pt-2">
                <FormField label="Retention Occurrence" id="dedup-keep">
                  <div className="flex gap-4">
                    <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer">
                      <input
                        type="radio"
                        name="dedupKeep"
                        value="first"
                        checked={dedupKeep === 'first'}
                        onChange={(e) => setDedupKeep(e.target.value)}
                        className="text-brand-600 focus:ring-brand-500"
                      />
                      Keep First Occurrence
                    </label>
                    <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer">
                      <input
                        type="radio"
                        name="dedupKeep"
                        value="last"
                        checked={dedupKeep === 'last'}
                        onChange={(e) => setDedupKeep(e.target.value)}
                        className="text-brand-600 focus:ring-brand-500"
                      />
                      Keep Last Occurrence
                    </label>
                  </div>
                </FormField>
              </div>
            )}
          </div>
        </Card>

        {/* Panel 4: Outlier Treatment */}
        <Card
          title="Numerical Outlier Handling (IQR 1.5x)"
          subtitle="Mitigate extreme numerical skewness via statistical bounds"
        >
          <div className="space-y-4">
            <div className="p-3 bg-slate-50 rounded-lg flex items-start gap-3">
              <input
                type="checkbox"
                id="outlier-check"
                checked={outlierHandling}
                onChange={(e) => setOutlierHandling(e.target.checked)}
                className="mt-1 h-4 w-4 rounded-sm text-brand-600 focus:ring-brand-500 border-slate-300"
              />
              <label htmlFor="outlier-check" className="text-xs text-slate-700 cursor-pointer">
                <span className="font-semibold block text-slate-900">Enable Outlier Remediation</span>
                Evaluate numerical columns using Interquartile Range multiplier.
              </label>
            </div>

            {outlierHandling && (
              <>
                <FormField label="Target Numerical Column" id="outlier-col">
                  <select
                    id="outlier-col"
                    value={outlierColumn}
                    onChange={(e) => setOutlierColumn(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-xs font-medium text-slate-800"
                  >
                    {columnsList.map((col) => (
                      <option key={col} value={col}>
                        {col}
                      </option>
                    ))}
                  </select>
                </FormField>

                <FormField label="Treatment Mode" id="treatment-mode">
                  <select
                    id="treatment-mode"
                    value={outlierTreatment}
                    onChange={(e) => setOutlierTreatment(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-xs font-medium text-slate-800"
                  >
                    <option value="clip">Clip to Lower/Upper Bounds (Preserves rows)</option>
                    <option value="set_null">Set Outlier Cells to Null</option>
                  </select>
                </FormField>
              </>
            )}
          </div>
        </Card>
      </div>

      {/* Real In-Memory Preview Results */}
      {previewResult && (
        <div className="space-y-4 pt-4 border-t border-slate-200">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <Eye className="w-5 h-5 text-brand-600" />
              Proposed Transformation Preview (In-Memory)
            </h3>
            <Badge variant="brand">Calculated via FastAPI Engine</Badge>
          </div>

          {/* Metric Comparison Banner */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3.5 bg-white border border-slate-200 rounded-lg text-center">
              <p className="text-[11px] font-semibold text-slate-400 uppercase">Rows</p>
              <p className="text-base font-bold text-slate-900 mt-0.5">
                {previewResult.summary.rows.before} &rarr; {previewResult.summary.rows.after}
              </p>
              <span className={`text-[11px] font-medium ${previewResult.summary.rows.difference < 0 ? 'text-rose-600' : 'text-slate-500'}`}>
                {previewResult.summary.rows.difference} rows
              </span>
            </div>

            <div className="p-3.5 bg-white border border-slate-200 rounded-lg text-center">
              <p className="text-[11px] font-semibold text-slate-400 uppercase">Columns</p>
              <p className="text-base font-bold text-slate-900 mt-0.5">
                {previewResult.summary.columns.before} &rarr; {previewResult.summary.columns.after}
              </p>
              <span className="text-[11px] font-medium text-slate-400">
                {previewResult.summary.columns.difference} columns
              </span>
            </div>

            <div className="p-3.5 bg-white border border-slate-200 rounded-lg text-center">
              <p className="text-[11px] font-semibold text-slate-400 uppercase">Missing Cells</p>
              <p className="text-base font-bold text-slate-900 mt-0.5">
                {previewResult.summary.missing_cells.before} &rarr; {previewResult.summary.missing_cells.after}
              </p>
              <span className="text-[11px] font-medium text-emerald-600">
                {previewResult.summary.missing_cells.difference} missing
              </span>
            </div>

            <div className="p-3.5 bg-white border border-slate-200 rounded-lg text-center">
              <p className="text-[11px] font-semibold text-slate-400 uppercase">Duplicate Rows</p>
              <p className="text-base font-bold text-slate-900 mt-0.5">
                {previewResult.summary.duplicate_rows.before} &rarr; {previewResult.summary.duplicate_rows.after}
              </p>
              <span className="text-[11px] font-medium text-rose-600">
                {previewResult.summary.duplicate_rows.difference} duplicates
              </span>
            </div>
          </div>

          {/* Table Preview */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card title={`Original Preview (${previewResult.original_preview.length} rows)`}>
              <div className="overflow-x-auto text-xs font-mono -mx-5 -my-5 max-h-64">
                <table className="w-full text-left">
                  <thead className="bg-slate-50 border-b border-slate-100 text-[10px] text-slate-400 uppercase sticky top-0">
                    <tr>
                      {previewResult.columns.map((col) => (
                        <th key={col} className="p-2.5">
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    {previewResult.original_preview.map((row, idx) => (
                      <tr key={idx}>
                        {previewResult.columns.map((col) => (
                          <td key={col} className="p-2.5 whitespace-nowrap">
                            {row[col] == null ? <span className="text-rose-500 font-sans">&lt;null&gt;</span> : String(row[col])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>

            <Card title={`Cleaned Preview (${previewResult.cleaned_preview.length} rows)`}>
              <div className="overflow-x-auto text-xs font-mono -mx-5 -my-5 max-h-64">
                <table className="w-full text-left">
                  <thead className="bg-slate-50 border-b border-slate-100 text-[10px] text-slate-400 uppercase sticky top-0">
                    <tr>
                      {previewResult.columns.map((col) => (
                        <th key={col} className="p-2.5">
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    {previewResult.cleaned_preview.map((row, idx) => (
                      <tr key={idx}>
                        {previewResult.columns.map((col) => (
                          <td key={col} className="p-2.5 whitespace-nowrap">
                            {row[col] == null ? <span className="text-rose-500 font-sans">&lt;null&gt;</span> : String(row[col])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        </div>
      )}

      {/* Confirmation Modal Before Permanent Output Creation */}
      {showApplyConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-xs">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 max-w-md w-full p-6 space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-brand-50 text-brand-600 flex items-center justify-center shrink-0">
                <Sparkles className="w-5 h-5" />
              </div>
              <div>
                <h4 className="font-bold text-slate-900 text-base">
                  {isPublicDemo ? 'Generate Sample Cleaning?' : 'Apply Cleaning Operations?'}
                </h4>
                <p className="text-xs text-slate-500">
                  {isPublicDemo ? 'Confirm browser-only sample transformation' : 'Confirm permanent transformation'}
                </p>
              </div>
            </div>

            <p className="text-xs text-slate-600">
              {isPublicDemo
                ? <>This simulates supported transformations on fictional sample <strong>{selectedDataset?.original_filename}</strong> in temporary browser memory. No files are uploaded or saved.</>
                : <>This will execute transformations on <strong>{selectedDataset?.original_filename}</strong>, serialize a new cleaned CSV file, and record the job in your PostgreSQL history.</>}
            </p>

            <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-800">
              {isPublicDemo
                ? <><strong>Demo isolation:</strong> Only bundled fictional sample rows change; authenticated user files and records are not accessed.</>
                : <><strong>Immutability Guarantee:</strong> Your original uploaded file will not be overwritten or modified.</>}
            </div>

            <div className="flex justify-end gap-2.5 pt-2">
              <Button
                variant="ghost"
                onClick={() => setShowApplyConfirm(false)}
                disabled={isApplying}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleApply}
                isLoading={isApplying}
                disabled={isApplying}
              >
                {isPublicDemo ? 'Generate Sample' : 'Confirm & Clean'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
