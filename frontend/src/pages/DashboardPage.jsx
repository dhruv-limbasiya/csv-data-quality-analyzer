import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Database,
  BarChart3,
  Sparkles,
  FileUp,
  ArrowUpRight,
  CheckCircle2,
  AlertCircle,
  Loader2,
} from 'lucide-react';
import { Card, Button, Badge, PageHeader } from '../components/common/UI';
import { ScoreGauge, MissingDistributionChart } from '../components/charts/AnalyticsCharts';
import { datasetService } from '../services/datasetService';
import { analysisService } from '../services/analysisService';
import { cleaningService } from '../services/cleaningService';

export default function DashboardPage() {
  const navigate = useNavigate();

  const [datasets, setDatasets] = useState([]);
  const [featuredAnalysis, setFeaturedAnalysis] = useState(null);
  const [cleaningsCount, setCleaningsCount] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function loadDashboardData() {
      setIsLoading(true);
      setError(null);
      try {
        // 1. Fetch user datasets
        const dsRes = await datasetService.listDatasets();
        const dsList = dsRes.items || [];
        setDatasets(dsList);

        if (dsList.length > 0) {
          // 2. Fetch analysis for the most recent dataset
          try {
            const anaRes = await analysisService.getDatasetAnalyses(dsList[0].id, 0, 1);
            if (anaRes.items && anaRes.items.length > 0) {
              setFeaturedAnalysis({
                ...anaRes.items[0],
                datasetName: dsList[0].original_filename,
              });
            }
          } catch (e) {
            console.warn('No analysis found for featured dataset:', e);
          }

          // 3. Count cleanings across datasets
          let totalCleanings = 0;
          for (const ds of dsList.slice(0, 5)) {
            try {
              const clRes = await cleaningService.getDatasetCleanings(ds.id, 0, 10);
              totalCleanings += clRes.total || 0;
            } catch {
              // ignore
            }
          }
          setCleaningsCount(totalCleanings);
        }
      } catch (err) {
        setError(err.formattedMessage || 'Failed to load dashboard metrics.');
      } finally {
        setIsLoading(false);
      }
    }
    loadDashboardData();
  }, []);

  const totalRowsCount = datasets.reduce((acc, d) => acc + (d.row_count || 0), 0);
  const missingDistributionData =
    featuredAnalysis?.summary_stats?.columns_quality
      ?.filter((col) => col.missing_percentage > 0)
      ?.map((col) => ({
        name: col.name,
        missingPct: col.missing_percentage,
      })) || [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Analytics Overview"
        description="Monitor dataset health, quality metrics, and cleaning progress across all CSV repositories."
        actions={
          <Button
            variant="primary"
            icon={FileUp}
            onClick={() => navigate('/datasets')}
          >
            Upload New CSV
          </Button>
        }
      />

      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-700 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="py-16 flex flex-col items-center justify-center gap-3 text-slate-500">
          <Loader2 className="w-7 h-7 animate-spin text-brand-600" />
          <p className="text-xs font-medium">Loading analytics overview...</p>
        </div>
      ) : (
        <>
          {/* Top Stat Summary Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="border-l-4 border-l-brand-600">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Total Datasets</p>
              <p className="text-2xl font-bold text-slate-900 mt-1">{datasets.length}</p>
              <p className="text-xs text-slate-400 mt-0.5">Uploaded CSV repositories</p>
            </div>
            <div className="w-10 h-10 rounded-lg bg-brand-50 text-brand-600 flex items-center justify-center">
              <Database className="w-5 h-5" />
            </div>
          </div>
        </Card>

        <Card className="border-l-4 border-l-emerald-600">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Latest Quality Score</p>
              <p className="text-2xl font-bold text-slate-900 mt-1">
                {featuredAnalysis ? `${featuredAnalysis.overall_score}%` : '—'}
              </p>
              <p className="text-xs text-emerald-600 mt-0.5 font-medium">
                {featuredAnalysis ? featuredAnalysis.datasetName : 'No audit yet'}
              </p>
            </div>
            <div className="w-10 h-10 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
              <BarChart3 className="w-5 h-5" />
            </div>
          </div>
        </Card>

        <Card className="border-l-4 border-l-purple-600">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Cleaned Versions</p>
              <p className="text-2xl font-bold text-slate-900 mt-1">{cleaningsCount}</p>
              <p className="text-xs text-slate-400 mt-0.5">Completed jobs</p>
            </div>
            <div className="w-10 h-10 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center">
              <Sparkles className="w-5 h-5" />
            </div>
          </div>
        </Card>

        <Card className="border-l-4 border-l-amber-600">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Total Rows Evaluated</p>
              <p className="text-2xl font-bold text-slate-900 mt-1">{totalRowsCount.toLocaleString()}</p>
              <p className="text-xs text-slate-400 mt-0.5">Across {datasets.length} files</p>
            </div>
            <div className="w-10 h-10 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
              <CheckCircle2 className="w-5 h-5" />
            </div>
          </div>
        </Card>
      </div>

      {/* Main Charts & Quality Section */}
      {featuredAnalysis ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Card
            title="Featured Quality Health"
            subtitle={`Recent audit for ${featuredAnalysis.datasetName}`}
            headerAction={
              <Button
                variant="outline"
                size="sm"
                icon={ArrowUpRight}
                onClick={() => navigate('/quality', { state: { selectedDatasetId: featuredAnalysis.dataset_id } })}
              >
                Full Report
              </Button>
            }
          >
            <div className="flex flex-col items-center">
              <ScoreGauge score={featuredAnalysis.overall_score} size={170} />
              <div className="w-full mt-4 pt-4 border-t border-slate-100 grid grid-cols-3 gap-2 text-center">
                <div>
                  <p className="text-[11px] text-slate-400">Missing</p>
                  <p className="text-sm font-semibold text-slate-700">
                    {featuredAnalysis.summary_stats?.total_missing_cells ?? 0}
                  </p>
                </div>
                <div>
                  <p className="text-[11px] text-slate-400">Duplicates</p>
                  <p className="text-sm font-semibold text-slate-700">
                    {featuredAnalysis.summary_stats?.duplicate_rows ?? 0}
                  </p>
                </div>
                <div>
                  <p className="text-[11px] text-slate-400">Invalid</p>
                  <p className="text-sm font-semibold text-slate-700">
                    {featuredAnalysis.summary_stats?.total_invalid_values ?? 0}
                  </p>
                </div>
              </div>
            </div>
          </Card>

          <Card
            className="lg:col-span-2"
            title="Missing Values Distribution"
            subtitle="Percentage of missing records per column"
            headerAction={
              <Badge variant={missingDistributionData.length > 0 ? 'warning' : 'success'}>
                {missingDistributionData.length} Impacted
              </Badge>
            }
          >
            <MissingDistributionChart data={missingDistributionData} />
          </Card>
        </div>
      ) : (
        <Card className="py-8 text-center text-slate-500">
          <p className="text-sm font-medium text-slate-700">No Quality Audits Run Yet</p>
          <p className="text-xs text-slate-400 mt-1 mb-4">
            Upload a CSV and run your first quality assessment to unlock health metrics and distribution charts.
          </p>
          <Button variant="outline" size="sm" onClick={() => navigate('/datasets')}>
            Go to Datasets
          </Button>
        </Card>
      )}

      {/* Recent Datasets Table */}
      <Card
        title="Recent Dataset Activity"
        subtitle="Manage and analyze uploaded CSV data files"
        headerAction={
          <Button variant="ghost" size="sm" onClick={() => navigate('/datasets')}>
            View All
          </Button>
        }
      >
        {datasets.length === 0 ? (
          <p className="text-xs text-slate-400 py-4 text-center">No datasets in your workspace yet.</p>
        ) : (
          <div className="overflow-x-auto -mx-5 -mb-5">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-[11px] font-semibold text-slate-400 uppercase tracking-wider border-y border-slate-100">
                <tr>
                  <th className="py-3 px-5">Dataset Name</th>
                  <th className="py-3 px-5">Rows</th>
                  <th className="py-3 px-5">Cols</th>
                  <th className="py-3 px-5">File Size</th>
                  <th className="py-3 px-5">Type</th>
                  <th className="py-3 px-5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {datasets.slice(0, 5).map((ds) => (
                  <tr key={ds.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="py-3.5 px-5 font-medium text-slate-900 flex items-center gap-2.5">
                      <Database className="w-4 h-4 text-slate-400 shrink-0" />
                      <span>{ds.original_filename}</span>
                    </td>
                    <td className="py-3.5 px-5 font-mono text-xs">{ds.row_count != null ? ds.row_count.toLocaleString() : '—'}</td>
                    <td className="py-3.5 px-5 font-mono text-xs">{ds.column_count != null ? ds.column_count : '—'}</td>
                    <td className="py-3.5 px-5 text-xs">{(ds.file_size_bytes / 1024).toFixed(1)} KB</td>
                    <td className="py-3.5 px-5">
                      <Badge variant={ds.is_cleaned_version ? 'purple' : 'brand'}>
                        {ds.is_cleaned_version ? 'Cleaned' : 'Original'}
                      </Badge>
                    </td>
                    <td className="py-3.5 px-5 text-right">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => navigate('/quality', { state: { selectedDatasetId: ds.id } })}
                      >
                        Inspect
                      </Button>
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
