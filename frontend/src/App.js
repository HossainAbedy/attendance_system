import React, { useState, useEffect } from 'react';
import { useSnackbar } from 'notistack';
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
  const { enqueueSnackbar } = useSnackbar();

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

  // Show toaster when branches are loaded
  useEffect(() => {
    if (activeView === 'branches') {
      enqueueSnackbar('Loading branches...', { variant: 'info' });
    }
  }, [activeView, enqueueSnackbar]);

  async function fetchDevices(branchId = null) {
    setDevicesLoading(true);
    setDevicesError(null);
    setSelectedBranchForDevices(branchId);
    setActiveView('devices');

    enqueueSnackbar(
      branchId ? `Loading devices for branch ${branchId}...` : 'Loading all devices...',
      { variant: 'info' }
    );

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
      enqueueSnackbar('Devices loaded successfully', { variant: 'success' });
    } catch (error) {
      console.error('Failed to fetch devices', error);
      setDevicesError(true);
      setDevicesForBranch([]);
      enqueueSnackbar('Failed to load devices', { variant: 'error' });
    } finally {
      setDevicesLoading(false);
    }
  }

  function handleDevicesStatClick() {
    fetchDevices(null);
  }

  function handleShowDevices(branchId) {
    fetchDevices(branchId);
  }

  function handleBackFromDevices() {
    setActiveView('branches');
    setSelectedBranchForDevices(null);
    setDevicesForBranch([]);
  }

  function openLogsView(branchId = null) {
    setLogsBranchFilter(branchId);
    setActiveView('logs');
    enqueueSnackbar(branchId ? `Loading logs for branch ${branchId}...` : 'Loading all logs...', { variant: 'info' });
  }

  function openBranchesView() {
    setActiveView('branches');
  }

  return ( 
      <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
        <TopBar onRefresh={refreshBranches} onShowJobs={() => setJobsOpen(true)} isRefreshing={loading} />
        <Container maxWidth="xl" disableGutters sx={{ py: 3 }}>
          <Box sx={{ display: 'flex', gap: 2, alignItems: 'flex-start', flexDirection: { xs: 'column', md: 'row' } }}>
            <Box sx={{ flex: '0 0 70%', minWidth: 0 }}>
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

            <Box sx={{ flex: '0 0 30%', minWidth: 280, display: 'flex', flexDirection: 'column', gap: 5 }}>
              <Card
                sx={{
                  borderRadius: 3,
                  boxShadow: '0 8px 24px rgba(0,0,0,0.08)',
                  overflow: 'hidden',
                  background: 'linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%)',
                }}
              >
                <CardContent>
                  <Typography
                    variant="h6"
                    gutterBottom
                    sx={{
                      fontWeight: 700,
                      color: 'text.primary',
                      borderBottom: '2px solid',
                      borderColor: 'primary.main',
                      pb: 0.5,
                    }}
                  >
                    Overview
                  </Typography>

                  <Box sx={{ mt: 2, display: 'grid', gap: 2 }}>
                    <StatCard
                      title="Branches"
                      value={branches?.length ?? '-'}
                      onClick={openBranchesView}
                      icon={<CloudQueueIcon fontSize="large" sx={{ color: '#fff' }} />}
                      bgColor="linear-gradient(135deg, #ff5f6d 0%, #ffc371 100%)" // red-orange gradient
                      sx={{
                        borderRadius: 2,
                        boxShadow: '0 6px 16px rgba(255,95,109,0.25)',
                        transition: 'transform 0.15s ease, box-shadow 0.15s ease',
                        '&:hover': {
                          transform: 'translateY(-2px)',
                          boxShadow: '0 10px 26px rgba(255,95,109,0.35)',
                        },
                      }}
                    />

                    <StatCard
                      title="Devices"
                      value={devicesCount ?? '-'}
                      onClick={handleDevicesStatClick}
                      icon={<DeviceHubIcon fontSize="large" sx={{ color: '#fff' }} />}
                      bgColor="linear-gradient(135deg, #36d1dc 0%, #5b86e5 100%)" // blue gradient
                      sx={{
                        borderRadius: 2,
                        boxShadow: '0 6px 16px rgba(91,134,229,0.25)',
                        transition: 'transform 0.15s ease, box-shadow 0.15s ease',
                        '&:hover': {
                          transform: 'translateY(-2px)',
                          boxShadow: '0 10px 26px rgba(91,134,229,0.35)',
                        },
                      }}
                    />

                    <StatCard
                      title="Logs"
                      value={logsCount ?? '-'}
                      onClick={() => openLogsView(null)}
                      icon={<SyncIcon fontSize="large" sx={{ color: '#fff' }} />}
                      bgColor="linear-gradient(135deg, #00b09b 0%, #96c93d 100%)" // green gradient
                      sx={{
                        borderRadius: 2,
                        boxShadow: '0 6px 16px rgba(0,176,155,0.25)',
                        transition: 'transform 0.15s ease, box-shadow 0.15s ease',
                        '&:hover': {
                          transform: 'translateY(-2px)',
                          boxShadow: '0 10px 26px rgba(0,176,155,0.35)',
                        },
                      }}
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
