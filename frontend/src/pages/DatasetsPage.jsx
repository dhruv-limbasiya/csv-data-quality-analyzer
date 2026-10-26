import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Database,
  FileUp,
  Search,
  Filter,
  BarChart3,
  Sparkles,
  AlertCircle,
  RefreshCw,
  CheckCircle2,
} from 'lucide-react';
import { Card, Button, Badge, PageHeader, EmptyState } from '../components/common/UI';
import { datasetService } from '../services/datasetService';

const MAX_UPLOAD_SIZE_MB = Math.max(1, Math.min(5, Number(import.meta.env.VITE_MAX_UPLOAD_SIZE_MB) || 5));

export default function DatasetsPage() {
  const navigate = useNavigate();

  const [datasets, setDatasets] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  const [searchTerm, setSearchTerm] = useState('');
  const [filterType, setFilterType] = useState('all');

  // Upload modal state
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [uploadSuccess, setUploadSuccess] = useState(false);
  const uploadController = useRef(null);

  const fetchDatasets = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await datasetService.listDatasets();
      setDatasets(data.items || []);
    } catch (err) {
      setError(err.formattedMessage || 'Failed to retrieve datasets.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDatasets();
  }, [fetchDatasets]);

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    setUploadError(null);
    setUploadSuccess(false);
    if (!file) {
      setUploadFile(null);
      return;
    }
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setUploadError('Only CSV files (.csv) are supported.');
      setUploadFile(null);
      return;
    }
    if (file.size > MAX_UPLOAD_SIZE_MB * 1024 * 1024) {
      setUploadError(`File exceeds maximum upload size of ${MAX_UPLOAD_SIZE_MB} MB.`);
      setUploadFile(null);
      return;
    }
    setUploadFile(file);
  };

  const handleUploadSubmit = async (e) => {
    e.preventDefault();
    if (!uploadFile) {
      setUploadError('Please choose a CSV file to upload.');
      return;
    }

    setIsUploading(true);
    uploadController.current = new AbortController();
    setUploadProgress(0);
    setUploadError(null);

    try {
      await datasetService.uploadDataset(uploadFile, (progress) => {
        setUploadProgress(progress);
      }, { signal: uploadController.current.signal });
      setUploadSuccess(true);
      setUploadFile(null);
      await fetchDatasets();
      setTimeout(() => {
        setShowUploadModal(false);
        setUploadSuccess(false);
        setUploadProgress(0);
      }, 1000);
    } catch (err) {
      setUploadError(err.name === 'CanceledError' || err.name === 'AbortError'
        ? 'Upload canceled.'
        : (err.formattedMessage || 'Failed to upload CSV dataset.'));
    } finally {
      uploadController.current = null;
      setIsUploading(false);
    }
  };

  // Client-side search and filtering over real datasets
  const filteredDatasets = datasets.filter((ds) => {
    const matchesSearch = ds.original_filename.toLowerCase().includes(searchTerm.toLowerCase());
    const isCleaned = ds.is_cleaned_version;
    const matchesFilter =
      filterType === 'all' ||
      (filterType === 'cleaned' && isCleaned) ||
      (filterType === 'original' && !isCleaned);
    return matchesSearch && matchesFilter;
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Datasets Repository"
        description="View, search, and upload structured CSV datasets for comprehensive data quality assessment."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              icon={RefreshCw}
              onClick={fetchDatasets}
              disabled={isLoading}
            >
              Refresh
            </Button>
            <Button
              variant="primary"
              icon={FileUp}
              onClick={() => {
                setUploadError(null);
                setUploadSuccess(false);
                setUploadFile(null);
                setShowUploadModal(true);
              }}
            >
              Upload CSV
            </Button>
          </div>
        }
      />

      {/* Filter and Search Bar */}
      <Card className="p-4">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="relative w-full sm:w-80">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search datasets by filename..."
              className="w-full pl-9 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-hidden focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500"
            />
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto">
            <Filter className="w-4 h-4 text-slate-400 shrink-0" />
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-xs font-medium text-slate-700 focus:outline-hidden focus:ring-2 focus:ring-brand-500/20"
            >
              <option value="all">All Datasets ({datasets.length})</option>
              <option value="original">Original Uploads</option>
              <option value="cleaned">Cleaned Versions</option>
            </select>
          </div>
        </div>
      </Card>

      {/* Main Content Area */}
      {isLoading ? (
        <div className="py-16 text-center">
          <svg className="animate-spin h-8 w-8 text-brand-600 mx-auto mb-3" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
          </svg>
          <p className="text-xs text-slate-500">Loading datasets from PostgreSQL repository...</p>
        </div>
      ) : error ? (
        <div className="p-6 bg-rose-50 border border-rose-200 rounded-xl text-center">
          <AlertCircle className="w-8 h-8 text-rose-600 mx-auto mb-2" />
          <h4 className="font-semibold text-rose-900 text-sm">Failed to Load Datasets</h4>
          <p className="text-xs text-rose-700 mt-1 mb-4">{error}</p>
          <Button variant="outline" size="sm" onClick={fetchDatasets}>
            Retry
          </Button>
        </div>
      ) : filteredDatasets.length === 0 ? (
        <EmptyState
          icon={Database}
          title="No datasets found"
          description={
            searchTerm
              ? `No datasets matched "${searchTerm}".`
              : "You haven't uploaded any CSV datasets yet. Upload your first dataset to start analysis."
          }
          action={
            <Button
              variant="outline"
              size="sm"
              icon={FileUp}
              onClick={() => setShowUploadModal(true)}
            >
              Upload CSV File
            </Button>
          }
        />
      ) : (
        <Card>
          <div className="overflow-x-auto -mx-5 -my-5">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50/75 text-[11px] font-semibold text-slate-400 uppercase tracking-wider border-b border-slate-100">
                <tr>
                  <th className="py-3 px-5">Dataset Details</th>
                  <th className="py-3 px-5">Dimensions</th>
                  <th className="py-3 px-5">File Size</th>
                  <th className="py-3 px-5">Upload Date</th>
                  <th className="py-3 px-5">Type</th>
                  <th className="py-3 px-5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredDatasets.map((ds) => (
                  <tr key={ds.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="py-4 px-5">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-lg bg-brand-50 text-brand-600 flex items-center justify-center shrink-0">
                          <Database className="w-4 h-4" />
                        </div>
                        <div>
                          <p className="font-semibold text-slate-900">{ds.original_filename}</p>
                          <p className="text-[11px] text-slate-400">ID: #{ds.id}</p>
                        </div>
                      </div>
                    </td>
                    <td className="py-4 px-5">
                      <p className="text-xs font-medium text-slate-700">
                        {ds.row_count != null ? ds.row_count.toLocaleString() : '—'} rows
                      </p>
                      <p className="text-[11px] text-slate-400">
                        {ds.column_count != null ? ds.column_count : '—'} columns
                      </p>
                    </td>
                    <td className="py-4 px-5 text-xs text-slate-600 font-mono">
                      {(ds.file_size_bytes / 1024).toFixed(1)} KB
                    </td>
                    <td className="py-4 px-5 text-xs text-slate-500">
                      {new Date(ds.created_at).toLocaleDateString(undefined, {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                      })}
                    </td>
                    <td className="py-4 px-5">
                      <Badge variant={ds.is_cleaned_version ? 'purple' : 'brand'}>
                        {ds.is_cleaned_version ? 'Cleaned Output' : 'Original Upload'}
                      </Badge>
                    </td>
                    <td className="py-4 px-5 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <Button
                          variant="outline"
                          size="sm"
                          icon={BarChart3}
                          onClick={() => navigate('/quality', { state: { selectedDatasetId: ds.id } })}
                        >
                          Analyze
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          icon={Sparkles}
                          onClick={() => navigate('/cleaning', { state: { selectedDatasetId: ds.id } })}
                        >
                          Clean
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Real Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-xs">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 max-w-md w-full p-6">
            <h3 className="text-lg font-bold text-slate-900">Upload CSV Dataset</h3>
            <p className="text-xs text-slate-500 mt-1 mb-4">
              Select a valid UTF-8 CSV file up to {MAX_UPLOAD_SIZE_MB} MB in size.
            </p>

            <form onSubmit={handleUploadSubmit} className="space-y-4">
              {uploadError && (
                <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-700 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{uploadError}</span>
                </div>
              )}

              {uploadSuccess && (
                <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-700 flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                  <span>Upload and structural parsing completed successfully!</span>
                </div>
              )}

              <label className="border-2 border-dashed border-slate-200 hover:border-brand-500 rounded-xl p-8 text-center cursor-pointer transition-colors bg-slate-50/50 block">
                <input
                  type="file"
                  accept=".csv,text/csv"
                  onChange={handleFileChange}
                  className="hidden"
                  disabled={isUploading}
                />
                <FileUp className="w-10 h-10 text-slate-400 mx-auto mb-2" />
                <p className="text-sm font-semibold text-slate-700">
                  {uploadFile ? uploadFile.name : 'Click to select CSV file'}
                </p>
                <p className="text-xs text-slate-400 mt-1">
                  {uploadFile ? `${(uploadFile.size / 1024).toFixed(1)} KB` : `Max size ${MAX_UPLOAD_SIZE_MB} MB`}
                </p>
              </label>

              {isUploading && (
                <div className="space-y-1.5">
                  <div className="flex justify-between text-xs text-slate-500 font-medium">
                    <span>Uploading securely and parsing...</span>
                    <span>{uploadProgress}%</span>
                  </div>
                  <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-brand-600 transition-all duration-200"
                      style={{ width: `${uploadProgress}%` }}
                    />
                  </div>
                </div>
              )}

              <div className="mt-6 flex justify-end gap-2.5">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    if (isUploading) uploadController.current?.abort();
                    else setShowUploadModal(false);
                  }}
                >
                  {isUploading ? 'Cancel upload' : 'Cancel'}
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                  isLoading={isUploading}
                  disabled={!uploadFile || isUploading}
                >
                  Upload & Analyze
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
