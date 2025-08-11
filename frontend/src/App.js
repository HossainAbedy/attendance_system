// FILE: src/App.jsx
import React, { useState } from 'react';
import {
  Container,
  Grid,
  Card,
  CardContent,
  Box,
  CircularProgress,
  Dialog,
  Typography,
} from '@mui/material';
import {
  CloudQueue as CloudQueueIcon,
  DeviceHub as DeviceHubIcon,
  Sync as SyncIcon,
} from '@mui/icons-material';

import StatCard from './components/StatCard';
import BranchesTable from './components/BranchesTable';
import JobsTable from './components/JobsTable';
import TopBar from './components/TopBar';
import DetailsDialog from './components/DetailsDialog';
import SyncControls from './components/SyncControls';
import QuickActions from './components/QuickActions';
import LogsViewer from './components/LogsViewer';
import DevicesTable from "./components/DevicesTable";

import { getAllDevices, getBranchDevices } from './api';  // Only import getDevices now
import useBranches from './hooks/useBranches';
import useSync from './hooks/useSync';

export default function App() {
  const {
    branches = [],
    loading = false,
    devicesCount = 0,
    logsCount = 0,
    refreshBranches,
    createBranch,
    updateBranch,
    deleteBranch,
    createDevice,
    updateDevice,
    deleteDevice,
  } = useBranches();

  const { jobs = [], jobsOpen = false, setJobsOpen, actions, state } = useSync(refreshBranches);
  const [dialog, setDialog] = useState({ open: false, type: null, props: {} });

  const [activeView, setActiveView] = useState('branches');
  const [logsBranchFilter, setLogsBranchFilter] = useState(null);

  const [devicesForBranch, setDevicesForBranch] = useState([]);
  const [devicesLoading, setDevicesLoading] = useState(false);
  const [devicesError, setDevicesError] = useState(null);
  const [selectedBranchForDevices, setSelectedBranchForDevices] = useState(null);

  function openBranchesDialog() {
    setDialog({
      open: true,
      type: 'branches',
      props: {
        branches,
        onCreate: createBranch,
        onUpdate: updateBranch,
        onDelete: deleteBranch,
        onFetch: actions.handleFetchBranch,
        onShowDevices: handleShowDevices,
      },
    });
  }

  async function fetchDevices(branchId = null) {
    console.log('fetchDevices called with branchId:', branchId);

    setDevicesLoading(true);
    setDevicesError(null);
    setSelectedBranchForDevices(branchId);
    setActiveView('devices');

    try {
      let devices = [];
      if (branchId) {
        const res = await getBranchDevices(branchId);
        console.log('Raw data from getBranchDevices:', res);
        // if backend returns array directly
        devices = Array.isArray(res) ? res : res.devices ?? [];
      } else {
        const res = await getAllDevices();
        devices = res.devices ?? [];
      }
      console.log('Fetched devices:', devices);
      setDevicesForBranch(devices);
    } catch (error) {
      console.error('Failed to fetch devices', error);
      setDevicesError(true);
      setDevicesForBranch([]);
    } finally {
      setDevicesLoading(false);
    }
  }

  function handleDevicesStatClick() {
    fetchDevices(null); // fetch all devices
  }

  function handleShowDevices(branchId) {
    fetchDevices(branchId); // fetch devices for specific branch
  }

  function handleBackFromDevices() {
    setActiveView('branches');
    setSelectedBranchForDevices(null);
    setDevicesForBranch([]);
  }

  function openLogsView(branchId = null) {
    setLogsBranchFilter(branchId);
    setActiveView('logs');
  }

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <TopBar onRefresh={refreshBranches} onShowJobs={() => setJobsOpen(true)} />

      <Container sx={{ py: 3, maxWidth: 'xl' }}>
        <Grid container spacing={2}>
          <Grid item xs={12} md={8}>
            <Card sx={{ mb: 2 }}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Sync Controls
                </Typography>
                <SyncControls actions={actions} state={state} />
              </CardContent>
            </Card>

            <Card>
              <CardContent>
                {loading ? (
                  <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
                    <CircularProgress />
                  </Box>
                ) : (
                  <>
                    {activeView === 'branches' && (
                      <BranchesTable
                        branches={branches}
                        onFetch={actions.handleFetchBranch}
                        onShowDevices={handleShowDevices}
                        onCreate={createBranch}
                        onUpdate={updateBranch}
                        onDelete={deleteBranch}
                        onShowLogs={(branchId) => openLogsView(branchId)}
                      />
                    )}

                    {activeView === 'logs' && (
                      <LogsViewer
                        branchId={logsBranchFilter}
                        onBack={() => {
                          setActiveView('branches');
                          setLogsBranchFilter(null);
                        }}
                      />
                    )}

                    {activeView === 'devices' && (
                      <DevicesTable
                        devices={devicesForBranch}
                        loading={devicesLoading}
                        error={devicesError}
                        branchId={selectedBranchForDevices}
                        onBack={handleBackFromDevices}
                        onCreate={createDevice}
                        onUpdate={updateDevice}
                        onDelete={deleteDevice}
                        onFetch={actions.handleFetchBranch}
                      />
                    )}
                  </>
                )}
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Card sx={{ mb: 2 }}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Stats
                </Typography>
                <Box sx={{ display: 'grid', gap: 1 }}>
                  <StatCard
                    title="Branches"
                    value={branches?.length ?? '-'}
                    onClick={openBranchesDialog}
                    icon={<CloudQueueIcon fontSize="large" />}
                    bgColor="red"
                  />
                  <StatCard
                    title="Devices"
                    value={devicesCount ?? '-'}
                    onClick={handleDevicesStatClick}
                    icon={<DeviceHubIcon fontSize="large" />}
                    bgColor="blue"
                  />
                  <StatCard
                    title="Logs"
                    value={logsCount ?? '-'}
                    onClick={() => openLogsView(null)}
                    icon={<SyncIcon fontSize="large" />}
                    bgColor="green"
                  />
                </Box>
              </CardContent>
            </Card>

            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Quick Actions
                </Typography>
                <QuickActions actions={actions} setJobsOpen={setJobsOpen} />
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </Container>

      <DetailsDialog
        dialog={dialog}
        onClose={() => setDialog({ open: false, type: null, props: {} })}
        onPoll={actions.handlePollDevice}
      />

      <Dialog open={jobsOpen} onClose={() => setJobsOpen(false)} fullWidth maxWidth="md">
        <Box sx={{ p: 2 }}>
          <Typography variant="h6" gutterBottom>
            Sync Jobs
          </Typography>
          <JobsTable jobs={jobs} />
          <Box sx={{ mt: 2, textAlign: 'right' }}>
            <button onClick={() => setJobsOpen(false)}>Close</button>
          </Box>
        </Box>
      </Dialog>
    </Box>
  );
}
