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

import useBranches from './hooks/useBranches';
import useSync from './hooks/useSync';

export default function App() {
  const {
    branches = [],
    loading = false,
    devicesCount = 0,
    logsCount = 0,
    refreshBranches,
    getDevices,
    createBranch,
    updateBranch,
    deleteBranch,
    createDevice,
    updateDevice,
    deleteDevice,
  } = useBranches();

  const { jobs = [], jobsOpen = false, setJobsOpen, actions, state } = useSync(refreshBranches);
  const [dialog, setDialog] = useState({ open: false, type: null, props: {} });

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

  async function handleShowDevices(branchId) {
    setDialog({
      open: true,
      type: 'devices',
      props: { loading: true, branchId, devices: [], onCreate: createDevice, onUpdate: updateDevice, onDelete: deleteDevice, onFetch: actions.handleFetchBranch },
    });

    const { devices, error } = await getDevices(branchId);
    setDialog({
      open: true,
      type: 'devices',
      props: { loading: false, branchId, devices: error ? null : devices, error: !!error, onCreate: createDevice, onUpdate: updateDevice, onDelete: deleteDevice, onFetch: actions.handleFetchBranch },
    });
  }

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <TopBar onRefresh={refreshBranches} onShowJobs={() => setJobsOpen(true)} />

      <Container sx={{ py: 3, maxWidth: 'xl' }}>
        {/* Two-column layout: LEFT = Sync + Branches, RIGHT = Stats + Quick Actions */}
        <Grid container spacing={2}>
          {/* LEFT COLUMN (70%) */}
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
                <Typography variant="h6" gutterBottom>
                  Branches
                </Typography>
                {loading ? (
                  <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
                    <CircularProgress />
                  </Box>
                ) : (
                  <BranchesTable
                    branches={branches}
                    onFetch={actions.handleFetchBranch}
                    onShowDevices={handleShowDevices}
                    onCreate={createBranch}
                    onUpdate={updateBranch}
                    onDelete={deleteBranch}
                  />
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* RIGHT COLUMN (30%) */}
          <Grid item xs={12} md={4}>
            {/* Stats moved here */}
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
                    onClick={() =>
                      setDialog({
                        open: true,
                        type: 'info',
                        props: { title: 'Devices', content: <div>Use Branch → Devices to view devices</div> },
                      })
                    }
                    icon={<DeviceHubIcon fontSize="large" />}
                    bgColor="blue"
                  />
                  <StatCard
                    title="Logs"
                    value={logsCount ?? '-'}
                    onClick={() =>
                      setDialog({
                        open: true,
                        type: 'info',
                        props: { title: 'Logs', content: <div>Logs viewer not implemented (server-driven)</div> },
                      })
                    }
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

      {/* Dialogs */}
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
