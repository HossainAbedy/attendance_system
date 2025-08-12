// FILE: src/api.js
import axios from 'axios';

export const API_BASE = process.env.REACT_APP_API_BASE || 'http://localhost:5000';
export const SOCKET_URL = 'http://localhost:5000';

/**
 * Backend routes
 */
export const ENDPOINTS = {
  // Branches (list + create)
  branches: '/api/devices',

  // Single branch (update, delete)
  branch: (branchId) => `/api/devices/${branchId}`,

  // Single device (get, update, delete)
  device: (deviceId) => `/api/devices/device/${deviceId}`,

  // Ping device
  pollDevice: (deviceId) => `/api/devices/device/${deviceId}/ping`,
  pollDeviceLegacy: (deviceId) => `/api/logs/poll/${deviceId}`,

  // Logs endpoint
  logs: '/api/logs',
  logsByDevice: (deviceId) => `/api/logs/device/${deviceId}`,

  // Sync endpoints
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
 * Convenience helpers
 */
export const getBranches = () => api.get(ENDPOINTS.branches);
export const createBranch = (payload) => api.post(ENDPOINTS.branches, payload);
export const updateBranch = (branchId, payload) => api.put(ENDPOINTS.branch(branchId), payload);
export const deleteBranch = (branchId) => api.delete(ENDPOINTS.branch(branchId));

// IMPORTANT: Removed getBranchDevices and branchDevices endpoint - not supported by backend

export const createDevice = (branchId, payload) =>
  api.post(`${ENDPOINTS.branches}?branch_id=${branchId}`, payload);

export const getDevice = (deviceId) => api.get(ENDPOINTS.device(deviceId));
export const updateDevice = (deviceId, payload) => api.put(ENDPOINTS.device(deviceId), payload);
export const deleteDevice = (deviceId) => api.delete(ENDPOINTS.device(deviceId));

export const pingDevice = (deviceId) => api.post(ENDPOINTS.pollDevice(deviceId));
export const pollDeviceLegacy = (deviceId) => api.post(ENDPOINTS.pollDeviceLegacy(deviceId));

export const getLogs = (params) => api.get(ENDPOINTS.logs, { params });
export const getLogsByDevice = (deviceId, params) =>
  api.get(ENDPOINTS.logsByDevice(deviceId), { params });

export const startSyncAll = () => api.post(ENDPOINTS.syncRoot);
export const startSyncOneLegacy = () => api.post(ENDPOINTS.syncOneLegacy);
export const startScheduler = () => api.post(ENDPOINTS.syncStart);
export const stopScheduler = () => api.post(ENDPOINTS.syncStop);
export const fetchBranch = (id) => api.post(ENDPOINTS.syncBranch(id));
export const getJobs = () => api.get(ENDPOINTS.jobs);
export const getJobStatus = (id) => api.get(ENDPOINTS.jobStatus(id));

// export const getBranchDevices = (branchId) => api.get(`/api/devices/${branchId}/devices`);
export const getBranchDevices = (branchId) => api.get(`/api/devices/${branchId}/devices`).then(res => res.data);

export async function getAllDevices() {
  const res = await axios.get(`${API_BASE}/api/devices/alldevices`);
  return res.data;
}
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
  getLogs,
  getLogsByDevice,
  startSyncAll,
  startSyncOneLegacy,
  startScheduler,
  stopScheduler,
  fetchBranch,
  getJobs,
  getJobStatus,
};
