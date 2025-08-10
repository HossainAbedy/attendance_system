// FILE: src/components/SyncControls.jsx
import React from 'react';
import { Box, Button } from '@mui/material';
import SyncIcon from '@mui/icons-material/Sync';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';
import ListIcon from '@mui/icons-material/List';

export default function SyncControls({ actions }) {
  return (
    <Box sx={{ mt: 1, display: 'flex', gap: 1 }}>
      <Button variant="contained" startIcon={<SyncIcon />} onClick={actions.handleTotalSync}>
        Full Sync (All Branches)
      </Button>

      <Button variant="outlined" startIcon={<PlayArrowIcon />} onClick={actions.handleStartScheduler}>
        Start Scheduler
      </Button>

      <Button variant="outlined" color="error" startIcon={<StopIcon />} onClick={actions.handleStopScheduler}>
        Stop Scheduler
      </Button>

      <Button variant="text" startIcon={<ListIcon />} onClick={actions.fetchJobs}>
        View Jobs
      </Button>
    </Box>
  );
}
