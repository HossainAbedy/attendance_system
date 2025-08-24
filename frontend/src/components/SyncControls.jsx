// FILE: src/components/SyncControls.jsx
import React from 'react';
import SyncIcon from '@mui/icons-material/Sync';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';
import ListIcon from '@mui/icons-material/List';
import { Stack, Box, Button, Tooltip, CircularProgress } from '@mui/material';

export default function SyncControls({ actions }) {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'center', mt: 3 }}>
    <Stack
      direction={{ xs: 'column', sm: 'row' }}
      spacing={2}
      alignItems="center"
      justifyContent="center"
      sx={{ flexWrap: 'wrap' }}
    >
      {/* Full Sync */}
      <Tooltip title="Fetch logs from all branches now">
        <span>
          <Button
            onClick={actions.handleTotalSync}
            startIcon={<SyncIcon />}
            sx={{
              px: 3,
              py: 1.2,
              borderRadius: 2,
              textTransform: 'none',
              fontWeight: 700,
              boxShadow: '0 8px 20px rgba(25,118,210,0.12)',
              background: 'linear-gradient(90deg,#00bfa5 0%,#1976d2 100%)',
              color: 'common.white',
              '&:hover': {
                background: 'linear-gradient(90deg,#00d7b0 0%,#115293 100%)',
                boxShadow: '0 10px 26px rgba(25,118,210,0.16)',
              },
            }}
          >
            {actions.isSyncing ? <CircularProgress size={18} color="inherit" sx={{ mr: 1 }} /> : null}
            Full Sync (All)
          </Button>
        </span>
      </Tooltip>

      {/* Start Scheduler */}
      <Tooltip title="Start recurring scheduler">
        <span>
          <Button
            variant="contained"
            color="success"
            onClick={actions.handleStartScheduler}
            startIcon={<PlayArrowIcon />}
            sx={{
              px: 3,
              py: 1.2,
              borderRadius: 2,
              textTransform: 'none',
              fontWeight: 700,
              boxShadow: '0 8px 20px rgba(56, 142, 60, 0.25)', // soft green glow
              background: 'linear-gradient(90deg, #66BB6A 0%, #2E7D32 100%)', // light green → deep green
              color: 'common.white',
              '&:hover': {
                background: 'linear-gradient(90deg, #81C784 0%, #1B5E20 100%)', // lighter green → darker green
                boxShadow: '0 10px 26px rgba(46, 125, 50, 0.35)', // stronger green glow
              },
            }}
          >
            {actions.isStarting ? <CircularProgress size={18} color="inherit" sx={{ mr: 1 }} /> : null}
            Start Scheduler
          </Button>
        </span>
      </Tooltip>

      {/* Stop Scheduler */}
      <Tooltip title="Stop recurring scheduler">
        <span>
          <Button
            variant="contained"
            color="error"
            onClick={actions.handleStopScheduler}
            startIcon={<StopIcon />}
            sx={{
              px: 3,
              py: 1.2,
              borderRadius: 2,
              textTransform: 'none',
              fontWeight: 700,
              boxShadow: '0 8px 20px rgba(244, 67, 54, 0.25)', // soft red glow
              background: 'linear-gradient(90deg, #FF7043 0%, #D32F2F 100%)', // coral → deep red
              color: 'common.white',
              '&:hover': {
                background: 'linear-gradient(90deg, #FF8A65 0%, #B71C1C 100%)', // lighter coral → darker red
                boxShadow: '0 10px 26px rgba(211, 47, 47, 0.35)', // stronger red glow
              },
            }}
          >
            {actions.isStopping ? <CircularProgress size={18} color="inherit" sx={{ mr: 1 }} /> : null}
            Stop Scheduler
          </Button>
        </span>
      </Tooltip>

      {/* View Jobs */}
      <Tooltip title="See recent sync jobs">
        <span>
          <Button
            variant="outlined"
            onClick={actions.fetchJobs}
            startIcon={<ListIcon />}
            sx={{
              px: 3,
              py: 1.2,
              borderRadius: 2,
              textTransform: 'none',
              fontWeight: 700,
              boxShadow: '0 8px 20px rgba(255, 183, 77, 0.25)', // warm orange/yellow glow
              background: 'linear-gradient(90deg, #FFD54F 0%, #FF9800 100%)', // yellow → orange
              color: 'common.white',
              '&:hover': {
                background: 'linear-gradient(90deg, #FFE082 0%, #FB8C00 100%)', // lighter yellow → deeper orange
                boxShadow: '0 10px 26px rgba(255, 152, 0, 0.35)', // stronger warm glow
              },
            }}
          >
            {actions.isLoadingJobs ? <CircularProgress size={18} sx={{ mr: 1 }} /> : null}
            View Jobs
          </Button>
        </span>
      </Tooltip>
    </Stack>
  </Box>
  );
}
