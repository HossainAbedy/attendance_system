// FILE: src/api.js
import axios from 'axios';

export const API_BASE = process.env.REACT_APP_API_BASE || 'http://localhost:5000';

/**
 * Backend routes (devices blueprint is mounted at /api/devices)
 */
export const ENDPOINTS = {
  // Branches (list + create)
  branches: '/api/devices/',

  // Single branch (update, delete)
  branch: (branchId) => `/api/devices/${branchId}`,

  // Devices under a branch (list + create)
  branchDevices: (branchId) => `/api/devices/${branchId}/devices`,

  // Single device (get, update, delete)
  device: (deviceId) => `/api/devices/device/${deviceId}`,

  // Ping device
  pollDevice: (deviceId) => `/api/devices/device/${deviceId}/ping`,
  pollDeviceLegacy: (deviceId) => `/api/logs/poll/${deviceId}`,

  // Sync endpoints (keep as you had them)
  syncRoot: '/api/sync/',
  syncOneLegacy: '/api/sync/one',
  syncStart: '/api/sync/start',
  syncStop: '/api/sync/stop',
  syncBranch: (id) => `/api/sync/branch/${id}`,
  jobs: '/api/sync/jobs',
  jobStatus: (jobId) => `/api/sync/job/${jobId}`,
};

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
});

/**
 * Convenience helpers (named exports) — use these from your hooks/components.
 * Also provide a default export object for legacy imports.
 */
export const getBranches = () => api.get(ENDPOINTS.branches);
export const createBranch = (payload) => api.post(ENDPOINTS.branches, payload);
export const updateBranch = (branchId, payload) => api.put(ENDPOINTS.branch(branchId), payload);
export const deleteBranch = (branchId) => api.delete(ENDPOINTS.branch(branchId));

export const getBranchDevices = (branchId) => api.get(ENDPOINTS.branchDevices(branchId));
export const createDevice = (branchId, payload) => api.post(ENDPOINTS.branchDevices(branchId), payload);

export const getDevice = (deviceId) => api.get(ENDPOINTS.device(deviceId));
export const updateDevice = (deviceId, payload) => api.put(ENDPOINTS.device(deviceId), payload);
export const deleteDevice = (deviceId) => api.delete(ENDPOINTS.device(deviceId));

export const pingDevice = (deviceId) => api.post(ENDPOINTS.pollDevice(deviceId));
export const pollDeviceLegacy = (deviceId) => api.post(ENDPOINTS.pollDeviceLegacy(deviceId));

export const startSyncAll = () => api.post(ENDPOINTS.syncRoot);
export const startSyncOneLegacy = () => api.post(ENDPOINTS.syncOneLegacy);
export const startScheduler = () => api.post(ENDPOINTS.syncStart);
export const stopScheduler = () => api.post(ENDPOINTS.syncStop);
export const fetchBranch = (id) => api.post(ENDPOINTS.syncBranch(id));
export const getJobs = () => api.get(ENDPOINTS.jobs);
export const getJobStatus = (id) => api.get(ENDPOINTS.jobStatus(id));

export default {
  api,
  ENDPOINTS,
  getBranches,
  createBranch,
  updateBranch,
  deleteBranch,
  getBranchDevices,
  createDevice,
  getDevice,
  updateDevice,
  deleteDevice,
  pingDevice,
  pollDeviceLegacy,
  startSyncAll,
  startSyncOneLegacy,
  startScheduler,
  stopScheduler,
  fetchBranch,
  getJobs,
  getJobStatus,
};
