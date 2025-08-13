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
              px: 2.5,
              py: 1,
              borderRadius: 2,
              textTransform: 'none',
              fontWeight: 600,
              boxShadow: '0 6px 16px rgba(25,118,210,0.08)',
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
              px: 2.5,
              py: 1,
              borderRadius: 2,
              textTransform: 'none',
              fontWeight: 600,
              boxShadow: '0 6px 16px rgba(211,47,47,0.08)',
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
              px: 2,
              py: 1,
              borderRadius: 2,
              textTransform: 'none',
              fontWeight: 600,
              borderWidth: 1.25,
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
