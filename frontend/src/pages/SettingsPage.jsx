import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Shield,
  LogOut,
} from 'lucide-react';
import { Card, Button, Badge, PageHeader, FormField } from '../components/common/UI';
import { useAuth } from '../context/AuthContext';

const MAX_UPLOAD_SIZE_MB = Math.max(1, Math.min(5, Number(import.meta.env.VITE_MAX_UPLOAD_SIZE_MB) || 5));

export default function SettingsPage() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <div className="space-y-6 max-w-4xl">
      <PageHeader
        title="Settings & Preferences"
        description="Manage your account profile, security credentials, and application defaults."
      />

      {/* Profile Section */}
      <Card title="User Profile" subtitle="Account identification and workspace owner details">
        <div className="space-y-4">
          <div className="flex items-center gap-4 pb-4 border-b border-slate-100">
            <div className="w-14 h-14 rounded-full bg-brand-700 text-white flex items-center justify-center font-bold text-lg uppercase shadow-xs">
              {user?.username ? user.username.substring(0, 2) : 'US'}
            </div>
            <div>
              <h4 className="font-semibold text-slate-900 text-base">{user?.username || 'Authenticated User'}</h4>
              <p className="text-xs text-slate-500">{user?.email}</p>
              <Badge variant="brand" size="sm" className="mt-1">
                Active Session
              </Badge>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <FormField label="Username" id="user-name">
              <input
                type="text"
                id="user-name"
                disabled
                value={user?.username || ''}
                className="w-full px-3 py-2 bg-slate-100 border border-slate-200 rounded-lg text-xs text-slate-700 cursor-not-allowed font-medium"
              />
            </FormField>

            <FormField label="Email Address" id="user-email">
              <input
                type="email"
                id="user-email"
                disabled
                value={user?.email || ''}
                className="w-full px-3 py-2 bg-slate-100 border border-slate-200 rounded-lg text-xs text-slate-700 cursor-not-allowed font-medium"
              />
            </FormField>
          </div>

          {user?.created_at && (
            <p className="text-[11px] text-slate-400">
              Account registered on {new Date(user.created_at).toLocaleDateString(undefined, { dateStyle: 'long' })}
            </p>
          )}
        </div>
      </Card>

      {/* Security & Authentication */}
      <Card title="Security & Authentication" subtitle="Session security parameters and active cookie state">
        <div className="space-y-4">
          <div className="p-3.5 bg-slate-50 rounded-lg flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <Shield className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-semibold text-slate-900">Session Cookie Protection</p>
                <p className="text-xs text-slate-500 mt-0.5">
                  Authenticated with an HttpOnly session cookie and active CSRF token protection.
                </p>
              </div>
            </div>
            <Badge variant="success">Secured</Badge>
          </div>

          <div className="flex items-center justify-between pt-2">
            <div>
              <p className="text-xs font-semibold text-slate-800">Sign Out of Session</p>
              <p className="text-xs text-slate-500">Revoke your cookie session on the server.</p>
            </div>
            <Button
              variant="outline"
              size="sm"
              icon={LogOut}
              onClick={handleLogout}
            >
              Sign Out
            </Button>
          </div>
        </div>
      </Card>

      {/* System Information */}
      <Card title="System Information" subtitle="Platform release details and backend connectivity">
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-xs">
          <div>
            <p className="text-slate-400 font-medium">Application</p>
            <p className="font-semibold text-slate-900 mt-0.5">CSV Data Quality Analyzer</p>
          </div>
          <div>
            <p className="text-slate-400 font-medium">Frontend Engine</p>
            <p className="font-semibold text-slate-900 mt-0.5">React + Vite + Tailwind</p>
          </div>
          <div>
            <p className="text-slate-400 font-medium">Backend API</p>
            <p className="font-semibold text-slate-900 mt-0.5">FastAPI + PostgreSQL</p>
          </div>
          <div>
            <p className="text-slate-400 font-medium">Quality Engine</p>
            <p className="font-semibold text-slate-900 mt-0.5">Pandas + NumPy</p>
          </div>
          <div>
            <p className="text-slate-400 font-medium">Upload File Limit</p>
            <p className="font-semibold text-slate-900 mt-0.5">{MAX_UPLOAD_SIZE_MB} MB</p>
          </div>
          <div>
            <p className="text-slate-400 font-medium">Phase Status</p>
            <p className="font-semibold text-emerald-600 mt-0.5">Phase 7 Connected</p>
          </div>
        </div>
      </Card>
    </div>
  );
}
