// FILE: src/hooks/useSync.jsx
import { useState, useCallback } from 'react';
import { startSyncAll, startSyncOneLegacy, startScheduler, stopScheduler, fetchBranch as apiFetchBranch, pingDevice as apiPingDevice, getJobs as apiGetJobs } from '../api';

export default function useSync(refreshBranches) {
  const [jobs, setJobs] = useState([]);
  const [jobsOpen, setJobsOpen] = useState(false);

  async function fetchJobs() {
    try {
      const res = await apiGetJobs();
      const j = Array.isArray(res.data) ? res.data : res.data?.jobs ?? [];
      setJobs(j);
      setJobsOpen(true);
      return j;
    } catch (err) {
      console.error('fetchJobs failed', err);
      return null;
    }
  }

  const tryPost = async (fn) => fn();

  const handleTotalSync = useCallback(async () => {
    try {
      try {
        await tryPost(startSyncAll);
      } catch {
        await tryPost(startSyncOneLegacy);
      }
      await fetchJobs();
    } catch (err) {
      console.error('handleTotalSync failed', err);
    }
  }, []);

  const handleStartScheduler = useCallback(async () => {
    try {
      await tryPost(startScheduler);
      await fetchJobs();
    } catch (err) {
      console.error('handleStartScheduler failed', err);
    }
  }, []);

  const handleStopScheduler = useCallback(async () => {
    try {
      await tryPost(stopScheduler);
      await fetchJobs();
    } catch (err) {
      console.error('handleStopScheduler failed', err);
    }
  }, []);

  const handleFetchBranch = useCallback(async (branchId) => {
    try {
      await tryPost(() => apiFetchBranch(branchId));
      await fetchJobs();
    } catch (err) {
      console.error('handleFetchBranch failed', err);
    }
  }, []);

  const handlePollDevice = useCallback(async (deviceId) => {
    try {
      await tryPost(() => apiPingDevice(deviceId));
      await fetchJobs();
    } catch (err) {
      console.error('handlePollDevice failed', err);
    }
  }, []);

  return {
    jobs,
    jobsOpen,
    setJobsOpen,
    actions: {
      handleTotalSync,
      handleStartScheduler,
      handleStopScheduler,
      handleFetchBranch,
      handlePollDevice,
      fetchJobs,
    },
  };
}

