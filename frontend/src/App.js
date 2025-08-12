// src/App.jsx
import React, { useState } from 'react';
import {
  Container,
  Box,
  Card,
  CardContent,
  CircularProgress,
  Dialog,
  Typography,
  Button,
  Stack,
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
import LiveTerminalAndNotifications from './components/LiveTerminalAndNotifications';

import { getAllDevices, getBranchDevices, SOCKET_URL } from './api';
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
    setDevicesLoading(true);
    setDevicesError(null);
    setSelectedBranchForDevices(branchId);
    setActiveView('devices');

    try {
      let devices = [];
      if (branchId) {
        const res = await getBranchDevices(branchId);
        devices = Array.isArray(res) ? res : res.devices ?? [];
      } else {
        const res = await getAllDevices();
        devices = res.devices ?? [];
      }
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
        {/* Flex layout: left 60%, right 40% */}
        <Box sx={{
          display: 'flex',
          gap: 2,
          alignItems: 'flex-start',
          // On small screens stack vertically
          flexDirection: { xs: 'column', md: 'row' }
        }}>
          {/* LEFT: 60% */}
          <Box sx={{
            flex: '0 0 60%',
            minWidth: 0 // important so children can shrink
          }}>
            <Stack spacing={2}>
              <Card sx={{ minHeight: 120 }}>
                <CardContent>
                  <Typography variant="h6" gutterBottom>Sync Controls</Typography>
                  <SyncControls actions={actions} state={state} />
                </CardContent>
              </Card>

              <Card sx={{ minHeight: 560 }}>
                <CardContent>
                  {loading ? (
                    <Box sx={{ display: 'flex', justifyContent: 'center', p: 6 }}>
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
            </Stack>
          </Box>

          {/* RIGHT: 40% */}
          <Box sx={{
            flex: '0 0 40%',
            minWidth: 280,      // friendly minimum
            display: 'flex',
            flexDirection: 'column',
            gap: 5
          }}>

             <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>Overview</Typography>
                <Box sx={{ mt: 1, display: 'grid', gap: 1 }}>
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
                <Typography variant="h6" gutterBottom>Live Activity</Typography>
                <LiveTerminalAndNotifications
                  socketUrl={SOCKET_URL}
                  containerWidth="100%"
                  notificationsHeight="180px"
                  terminalHeight="420px"
                />
              </CardContent>
            </Card>

            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>Quick Actions</Typography>
                <QuickActions actions={actions} setJobsOpen={setJobsOpen} />
              </CardContent>
            </Card>
          </Box>
        </Box>
      </Container>

      <DetailsDialog
        dialog={dialog}
        onClose={() => setDialog({ open: false, type: null, props: {} })}
        onPoll={actions.handlePollDevice}
      />

      <Dialog open={jobsOpen} onClose={() => setJobsOpen(false)} fullWidth maxWidth="md">
        <Box sx={{ p: 2 }}>
          <Typography variant="h6" gutterBottom>Sync Jobs</Typography>
          <JobsTable jobs={jobs} />
          <Box sx={{ mt: 2, textAlign: 'right' }}>
            <Button variant="contained" onClick={() => setJobsOpen(false)}>Close</Button>
          </Box>
        </Box>
      </Dialog>
    </Box>
  );
}
