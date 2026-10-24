import React, { useState, useEffect, useCallback } from 'react';
import {
  History,
  CheckCircle,
  FileSpreadsheet,
  ArrowDownToLine,
  AlertCircle,
  RefreshCw,
} from 'lucide-react';
import { Card, Button, Badge, PageHeader, EmptyState } from '../components/common/UI';
import { datasetService } from '../services/datasetService';
import { cleaningService } from '../services/cleaningService';

export default function CleaningHistoryPage() {
  const [datasets, setDatasets] = useState([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState('all');
  const [cleaningRecords, setCleaningRecords] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [downloadingId, setDownloadingId] = useState(null);

  // 1. Load user's datasets
  useEffect(() => {
    async function loadDatasets() {
      try {
        const data = await datasetService.listDatasets();
        setDatasets(data.items || []);
      } catch (err) {
        console.error('Failed to load datasets for filter:', err);
      }
    }
    loadDatasets();
  }, []);

  // 2. Fetch cleaning history across datasets
  const fetchCleanings = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const allDatasets = datasets.length > 0 ? datasets : (await datasetService.listDatasets()).items || [];
      if (datasets.length === 0) setDatasets(allDatasets);

      if (allDatasets.length === 0) {
        setCleaningRecords([]);
        setIsLoading(false);
        return;
      }

      const targetDatasets =
        selectedDatasetId === 'all'
          ? allDatasets
          : allDatasets.filter((d) => d.id.toString() === selectedDatasetId.toString());

      const recordsAccumulator = [];
      for (const ds of targetDatasets) {
        try {
          const res = await cleaningService.getDatasetCleanings(ds.id, 0, 50);
          const items = res.items || [];
          for (const item of items) {
            recordsAccumulator.push({
              ...item,
              datasetName: ds.original_filename,
            });
          }
        } catch (e) {
          console.warn(`Failed to fetch cleanings for dataset ${ds.id}:`, e);
        }
      }

      // Sort by creation date descending
      recordsAccumulator.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
      setCleaningRecords(recordsAccumulator);
    } catch (err) {
      setError(err.formattedMessage || 'Failed to retrieve cleaning records.');
    } finally {
      setIsLoading(false);
    }
  }, [datasets, selectedDatasetId]);

  useEffect(() => {
    fetchCleanings();
  }, [fetchCleanings]);

  // Real file download trigger
  const handleDownload = async (record) => {
    setDownloadingId(record.id);
    try {
      const origName = record.datasetName || 'dataset';
      const stem = origName.replace(/\.[^/.]+$/, '');
      const downloadName = `${stem}_cleaned_${record.id}.csv`;
      await cleaningService.downloadCleanedFile(record.id, downloadName);
    } catch (err) {
      alert(`Download failed: ${err.formattedMessage || err.message}`);
    } finally {
      setDownloadingId(null);
    }
  };

  const summarizeOperations = (summary) => {
    if (!summary || !summary.operations_applied) return 'Transformations applied';
    return summary.operations_applied.map((op) => op.description).join('; ') || 'Standard clean';
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Cleaning History"
        description="Audit log of previous data cleaning jobs, output metadata, and download access for cleaned datasets."
        actions={
          <Button
            variant="outline"
            size="sm"
            icon={RefreshCw}
            onClick={fetchCleanings}
            disabled={isLoading}
          >
            Refresh
          </Button>
        }
      />

      {/* Dataset Filter */}
      {datasets.length > 0 && (
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Filter by Dataset:
            </span>
            <select
              value={selectedDatasetId}
              onChange={(e) => setSelectedDatasetId(e.target.value)}
              className="px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-medium text-slate-800 focus:outline-hidden focus:ring-2 focus:ring-brand-500/20"
            >
              <option value="all">All Datasets ({datasets.length})</option>
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.original_filename}
                </option>
              ))}
            </select>
          </div>
        </Card>
      )}

      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-700 text-xs flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
          <Button variant="ghost" size="sm" onClick={fetchCleanings}>
            Retry
          </Button>
        </div>
      )}

      {isLoading ? (
        <div className="py-16 text-center">
          <svg className="animate-spin h-8 w-8 text-brand-600 mx-auto mb-3" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
          </svg>
          <p className="text-xs text-slate-500">Loading cleaning audit history from database...</p>
        </div>
      ) : cleaningRecords.length === 0 ? (
        <EmptyState
          icon={History}
          title="No cleaning history"
          description="You haven't run any data cleaning operations on this dataset yet. Configure an operation in the Cleaning Studio to generate your first cleaned CSV."
        />
      ) : (
        <Card>
          <div className="overflow-x-auto -mx-5 -my-5">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50/75 text-[11px] font-semibold text-slate-400 uppercase tracking-wider border-b border-slate-100">
                <tr>
                  <th className="py-3 px-5">Job ID</th>
                  <th className="py-3 px-5">Source Dataset</th>
                  <th className="py-3 px-5">Operations Applied</th>
                  <th className="py-3 px-5">Status</th>
                  <th className="py-3 px-5">Output Rows</th>
                  <th className="py-3 px-5">Execution Date</th>
                  <th className="py-3 px-5 text-right">Download</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {cleaningRecords.map((record) => (
                  <tr key={record.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="py-3.5 px-5 font-mono text-xs font-semibold text-slate-900">
                      #{record.id}
                    </td>
                    <td className="py-3.5 px-5 font-medium text-slate-800 flex items-center gap-2">
                      <FileSpreadsheet className="w-4 h-4 text-slate-400 shrink-0" />
                      <span>{record.datasetName || `Dataset #${record.dataset_id}`}</span>
                    </td>
                    <td className="py-3.5 px-5 text-xs text-slate-600 max-w-xs truncate" title={summarizeOperations(record.cleaning_summary)}>
                      {summarizeOperations(record.cleaning_summary)}
                    </td>
                    <td className="py-3.5 px-5">
                      <Badge variant={record.status === 'completed' ? 'success' : 'danger'}>
                        {record.status === 'completed' && <CheckCircle className="w-3 h-3 mr-1 inline" />}
                        {record.status}
                      </Badge>
                    </td>
                    <td className="py-3.5 px-5 font-mono text-xs font-semibold text-slate-800">
                      {record.output_row_count != null ? record.output_row_count.toLocaleString() : '—'} rows
                    </td>
                    <td className="py-3.5 px-5 text-xs text-slate-500">
                      {new Date(record.created_at).toLocaleString(undefined, {
                        dateStyle: 'medium',
                        timeStyle: 'short',
                      })}
                    </td>
                    <td className="py-3.5 px-5 text-right">
                      <Button
                        variant="outline"
                        size="sm"
                        icon={ArrowDownToLine}
                        isLoading={downloadingId === record.id}
                        disabled={downloadingId === record.id}
                        onClick={() => handleDownload(record)}
                      >
                        Download CSV
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
