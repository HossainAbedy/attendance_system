
// FILE: src/hooks/useBranches.jsx
import { useEffect, useState, useRef, useCallback } from 'react';
import {
  getBranches,
  createBranch as apiCreateBranch,
  updateBranch as apiUpdateBranch,
  deleteBranch as apiDeleteBranch,
  getBranchDevices as apiGetBranchDevices,
  createDevice as apiCreateDevice,
  getDevice as apiGetDevice,
  updateDevice as apiUpdateDevice,
  deleteDevice as apiDeleteDevice,
} from '../api';

export default function useBranches() {
  const [branches, setBranches] = useState([]);
  const [loading, setLoading] = useState(false);
  const abortRef = useRef(null);

  useEffect(() => {
    fetchAll();
    return () => abortRef.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const normalizeBranches = useCallback((arr = []) => {
    return arr.map((b) => ({
      id: b.id ?? b.branch_id,
      name: b.name ?? b.branch_name,
      ip_range: b.ip_range ?? b.ip_address ?? b.ip_address_range,
      online: false,
      device_count: b.device_count ?? (Array.isArray(b.devices) ? b.devices.length : 0),
      log_count: b.log_count ?? 0,
      raw: b,
    }));
  }, []);

  function recalcCounts(normalized) {
    const devices = normalized.reduce((s, b) => s + (b.device_count || 0), 0);
    const logs = normalized.reduce((s, b) => s + (b.log_count || 0), 0);
    return { devices, logs };
  }

  async function fetchAll() {
    if (abortRef.current) abortRef.current.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    setLoading(true);
    try {
      const res = await getBranches();
      const raw = Array.isArray(res.data) ? res.data : res.data?.branches ?? [];
      const normalized = normalizeBranches(raw).map((b) => ({ ...b, online: false }));
      setBranches(normalized);
      // background fetch statuses
      fetchOnlineStatuses(normalized).catch(() => {});
      return recalcCounts(normalized);
    } catch (err) {
      console.error('fetchAll branches failed', err);
      return null;
    } finally {
      setLoading(false);
    }
  }

  async function fetchOnlineStatuses(branchesList = []) {
    const statusMap = {};

    await Promise.allSettled(
        (branchesList || []).map(async (branch) => {
        try {
            const devices = await apiGetBranchDevices(branch.id);
            // devices is expected to be an array directly
            const deviceList = Array.isArray(devices) ? devices : devices?.devices ?? devices?.items ?? [];

            const pings = await Promise.allSettled(
            deviceList.map((d) =>
                apiGetDevice(d.id).then(() => true).catch(() => false)
            )
            );

            statusMap[branch.id] = pings.some(
            (p) => p.status === 'fulfilled' && p.value === true
            );
        } catch (err) {
            statusMap[branch.id] = false;
        }
        })
    );

    setBranches((old) =>
        old.map((b) => ({ ...b, online: statusMap[b.id] ?? b.online }))
    );
   }

  // --- Branch CRUD ---
  async function createBranch(payload) {
    try {
      const res = await apiCreateBranch(payload);
      // optimistic refresh
      await fetchAll();
      return { success: true, data: res.data };
    } catch (err) {
      console.error('createBranch failed', err);
      return { success: false, error: err };
    }
  }

  async function updateBranch(branchId, payload) {
    try {
      const res = await apiUpdateBranch(branchId, payload);
      await fetchAll();
      return { success: true, data: res.data };
    } catch (err) {
      console.error('updateBranch failed', err);
      return { success: false, error: err };
    }
  }

  async function deleteBranch(branchId) {
    try {
      await apiDeleteBranch(branchId);
      await fetchAll();
      return { success: true };
    } catch (err) {
      console.error('deleteBranch failed', err);
      return { success: false, error: err };
    }
  }

  // --- Device CRUD ---
  async function createDevice(branchId, payload) {
    try {
      const res = await apiCreateDevice(branchId, payload);
      await fetchAll();
      return { success: true, data: res.data };
    } catch (err) {
      console.error('createDevice failed', err);
      return { success: false, error: err };
    }
  }

  async function updateDevice(deviceId, payload) {
    try {
      const res = await apiUpdateDevice(deviceId, payload);
      await fetchAll();
      return { success: true, data: res.data };
    } catch (err) {
      console.error('updateDevice failed', err);
      return { success: false, error: err };
    }
  }

  async function deleteDevice(deviceId) {
    try {
      await apiDeleteDevice(deviceId);
      await fetchAll();
      return { success: true };
    } catch (err) {
      console.error('deleteDevice failed', err);
      return { success: false, error: err };
    }
  }

  async function getDevices(branchId) {
    try {
      const res = await apiGetBranchDevices(branchId);
      const devices = Array.isArray(res.data) ? res.data : res.data?.devices ?? res.data?.items ?? [];
      return { devices };
    } catch (err) {
      console.error('getDevices failed', err);
      return { devices: null, error: true };
    }
  }

  return {
    branches,
    loading,
    refreshBranches: fetchAll,
    getDevices,
    // branch CRUD
    createBranch,
    updateBranch,
    deleteBranch,
    // device CRUD
    createDevice,
    updateDevice,
    deleteDevice,
    counts: recalcCounts(branches),
    devicesCount: recalcCounts(branches).devices,
    logsCount: recalcCounts(branches).logs,
  };
}