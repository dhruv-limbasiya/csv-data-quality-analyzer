import React, { useState, useEffect, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  BarChart3,
  Sparkles,
  CheckCircle,
  FileSpreadsheet,
  RotateCcw,
  AlertCircle,
} from 'lucide-react';
import { Card, Button, Badge, PageHeader, EmptyState } from '../components/common/UI';
import { ScoreGauge, PenaltyBreakdownChart, MissingDistributionChart } from '../components/charts/AnalyticsCharts';
import { datasetService } from '../services/datasetService';
import { analysisService } from '../services/analysisService';
import { useAuth } from '../context/AuthContext';

export default function QualityPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { isPublicDemo } = useAuth();

  const [datasets, setDatasets] = useState([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState(
    location.state?.selectedDatasetId?.toString() || ''
  );

  const [analysis, setAnalysis] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState(null);

  // 1. Fetch user's datasets on mount
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
        setError(err.formattedMessage || 'Failed to load user datasets.');
      }
    }
    loadDatasets();
  }, []);

  // 2. Fetch analysis history for selected dataset
  const fetchAnalysisForDataset = useCallback(async (datasetId) => {
    if (!datasetId) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await analysisService.getDatasetAnalyses(datasetId, 0, 10);
      const items = data.items || [];
      if (items.length > 0) {
        setAnalysis(items[0]); // Most recent analysis
      } else {
        setAnalysis(null);
      }
    } catch (err) {
      setError(err.formattedMessage || 'Failed to load quality analysis history.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedDatasetId) {
      fetchAnalysisForDataset(selectedDatasetId);
    }
  }, [selectedDatasetId, fetchAnalysisForDataset]);

  // 3. Trigger new analysis via POST /api/datasets/{id}/analyze
  const handleRunAnalysis = async () => {
    if (!selectedDatasetId) return;
    setIsAnalyzing(true);
    setError(null);
    try {
      const newAnalysis = await analysisService.runAnalysis(selectedDatasetId);
      setAnalysis(newAnalysis);
      await fetchAnalysisForDataset(selectedDatasetId);
    } catch (err) {
      setError(err.formattedMessage || 'Failed to execute quality analysis.');
    } finally {
      setIsAnalyzing(false);
    }
  };

  const selectedDataset = datasets.find((d) => d.id.toString() === selectedDatasetId.toString());
  const penalties = analysis?.summary_stats?.score_breakdown || {};

  // Format missing values distribution from columns_quality for chart
  const missingDistributionData =
    analysis?.summary_stats?.columns_quality
      ?.filter((col) => col.missing_percentage > 0)
      ?.map((col) => ({
        name: col.name,
        missingPct: col.missing_percentage,
      })) || [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Data Quality Assessment"
        description={isPublicDemo
          ? 'Explore illustrative quality results for synthetic datasets. Demo audit values are precomputed examples.'
          : 'Comprehensive dataset audit covering missing values, duplicates, domain validity, and distribution statistics.'}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              icon={RotateCcw}
              onClick={handleRunAnalysis}
              isLoading={isAnalyzing}
              disabled={!selectedDatasetId || isAnalyzing || isLoading}
            >
              {isPublicDemo ? 'Show Sample Audit' : 'Run Audit'}
            </Button>
            <Button
              variant="primary"
              icon={Sparkles}
              disabled={!selectedDatasetId}
              onClick={() => navigate('/cleaning', { state: { selectedDatasetId } })}
            >
              Configure Cleaning
            </Button>
          </div>
        }
      />

      {/* Dataset Selector Bar */}
      <Card className="p-4 bg-slate-900 text-white border-slate-800">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <FileSpreadsheet className="w-5 h-5 text-brand-400 shrink-0" />
            <div>
              <span className="text-xs text-slate-400 font-medium">Select Dataset to Inspect:</span>
              <div className="flex items-center gap-2 mt-0.5">
                {datasets.length === 0 ? (
                  <span className="text-xs text-slate-400 italic">No datasets uploaded yet</span>
                ) : (
                  <select
                    value={selectedDatasetId}
                    onChange={(e) => setSelectedDatasetId(e.target.value)}
                    className="bg-slate-800 border border-slate-700 text-white text-sm font-semibold rounded-lg px-3 py-1.5 focus:outline-hidden focus:ring-2 focus:ring-brand-500"
                  >
                    {datasets.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.original_filename} ({d.row_count != null ? d.row_count.toLocaleString() : '?'} rows)
                      </option>
                    ))}
                  </select>
                )}
                {analysis && <Badge variant="brand">Audited</Badge>}
              </div>
            </div>
          </div>

          <div className="text-xs text-slate-400">
            Engine: <span className="font-semibold text-slate-200">Pandas + Composite Scoring</span>
          </div>
        </div>
      </Card>

      {/* Error Banner */}
      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-700 text-xs flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
          <Button variant="ghost" size="sm" onClick={() => fetchAnalysisForDataset(selectedDatasetId)}>
            Dismiss / Retry
          </Button>
        </div>
      )}

      {/* Loading State */}
      {isLoading ? (
        <div className="py-16 text-center">
          <svg className="animate-spin h-8 w-8 text-brand-600 mx-auto mb-3" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
          </svg>
          <p className="text-xs text-slate-500">Loading quality analysis for dataset...</p>
        </div>
      ) : !selectedDatasetId ? (
        <EmptyState
          icon={BarChart3}
          title="No dataset selected"
          description="Upload or select a dataset to inspect its data quality score and metrics."
          action={
            <Button variant="primary" size="sm" onClick={() => navigate('/datasets')}>
              Go to Datasets
            </Button>
          }
        />
      ) : !analysis ? (
        <EmptyState
          icon={BarChart3}
          title="No quality analysis yet"
          description={`Dataset "${selectedDataset?.original_filename || selectedDatasetId}" has not been audited yet.`}
          action={
            <Button
              variant="primary"
              size="sm"
              icon={RotateCcw}
              onClick={handleRunAnalysis}
              isLoading={isAnalyzing}
            >
              Run First Quality Audit
            </Button>
          }
        />
      ) : (
        <>
          {/* Quality Score and Penalties Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <Card title="Overall Quality Score" subtitle="Evaluated across 4 metric pillars">
              <ScoreGauge score={analysis.overall_score} size={180} />
              <div className="mt-4 pt-4 border-t border-slate-100 text-xs text-slate-600 space-y-1.5">
                <div className="flex justify-between">
                  <span className="text-slate-500">Total Rows:</span>
                  <span className="font-semibold font-mono">
                    {analysis.summary_stats?.total_rows?.toLocaleString() ?? '—'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Total Columns:</span>
                  <span className="font-semibold font-mono">
                    {analysis.summary_stats?.total_columns ?? '—'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Total Missing Cells:</span>
                  <span className="font-semibold font-mono text-amber-600">
                    {analysis.summary_stats?.total_missing_cells?.toLocaleString() ?? '—'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Duplicate Rows:</span>
                  <span className="font-semibold font-mono text-slate-700">
                    {analysis.summary_stats?.duplicate_rows?.toLocaleString() ?? '—'}
                  </span>
                </div>
              </div>
            </Card>

            <Card
              className="lg:col-span-2"
              title="Penalty & Health Breakdown"
              subtitle="Deductions based on missing cells, duplicate rows, invalid formats, and column variance"
            >
              <PenaltyBreakdownChart penalties={penalties} />
              <div className="mt-3 p-3 bg-slate-50 rounded-lg text-xs text-slate-600">
                <span className="font-semibold text-slate-800">Scoring Formula: </span>
                <code className="text-brand-700 font-mono text-[11px]">{penalties.formula || 'Composite'}</code>
              </div>
            </Card>
          </div>

          {/* Missing Distribution Chart (if missing cells present) */}
          {missingDistributionData.length > 0 && (
            <Card
              title="Missing Value Distribution by Column"
              subtitle="Columns containing empty, whitespace-only, or null cells"
              headerAction={
                <Badge variant="warning">{missingDistributionData.length} Columns Impacted</Badge>
              }
            >
              <MissingDistributionChart data={missingDistributionData} />
            </Card>
          )}

          {/* Actionable Recommendations */}
          {analysis.recommendations && analysis.recommendations.length > 0 && (
            <Card
              title="Actionable Cleaning Recommendations"
              subtitle="Recommended remediation steps detected by analysis engine"
            >
              <div className="space-y-2.5">
                {analysis.recommendations.map((rec, index) => (
                  <div
                    key={index}
                    className="p-3 bg-brand-50/50 border border-brand-100 rounded-lg flex items-start justify-between gap-3"
                  >
                    <div className="flex items-start gap-2.5">
                      <CheckCircle className="w-4 h-4 text-brand-600 shrink-0 mt-0.5" />
                      <span className="text-xs font-medium text-slate-800">{rec}</span>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      className="shrink-0 text-[11px] py-1 px-2.5"
                      onClick={() => navigate('/cleaning', { state: { selectedDatasetId } })}
                    >
                      Apply Fix
                    </Button>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Granular Issues Table */}
          <Card title="Detected Quality Issues" subtitle="Granular list of structural and cell-level violations">
            {(!analysis.issues || analysis.issues.length === 0) ? (
              <p className="text-xs text-emerald-700 py-3 font-medium">
                No quality issues detected! The dataset passes all format and completeness rules.
              </p>
            ) : (
              <div className="overflow-x-auto -mx-5 -my-5">
                <table className="w-full text-left text-sm text-slate-600">
                  <thead className="bg-slate-50/75 text-[11px] font-semibold text-slate-400 uppercase tracking-wider border-b border-slate-100">
                    <tr>
                      <th className="py-3 px-5">Severity</th>
                      <th className="py-3 px-5">Category</th>
                      <th className="py-3 px-5">Target Column</th>
                      <th className="py-3 px-5">Affected Count</th>
                      <th className="py-3 px-5">Description</th>
                      <th className="py-3 px-5">Rule Applied</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {analysis.issues.map((issue, idx) => (
                      <tr key={idx} className="hover:bg-slate-50/70 transition-colors">
                        <td className="py-3.5 px-5">
                          <Badge
                            variant={
                              issue.severity === 'error'
                                ? 'danger'
                                : issue.severity === 'warning'
                                ? 'warning'
                                : 'neutral'
                            }
                          >
                            {issue.severity}
                          </Badge>
                        </td>
                        <td className="py-3.5 px-5 font-mono text-xs font-medium text-slate-700">
                          {issue.category}
                        </td>
                        <td className="py-3.5 px-5 font-mono text-xs text-brand-700">
                          {issue.column || 'All Columns'}
                        </td>
                        <td className="py-3.5 px-5 font-mono text-xs font-semibold text-slate-900">
                          {issue.count != null ? issue.count.toLocaleString() : '—'}
                        </td>
                        <td className="py-3.5 px-5 text-xs text-slate-800">{issue.description}</td>
                        <td className="py-3.5 px-5 text-[11px] text-slate-400 font-mono">
                          {issue.rule_applied}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
