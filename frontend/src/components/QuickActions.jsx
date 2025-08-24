// FILE: src/components/QuickActions.jsx
import React from 'react';
import { Box, Button } from '@mui/material';
import DownloadIcon from '@mui/icons-material/CloudDownload';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';
import ListIcon from '@mui/icons-material/List';

export default function QuickActions({ actions, setJobsOpen }) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, mt: 2 }}>
      <Button startIcon={<DownloadIcon />} onClick={actions.handleTotalSync}>
        Sync Now (All)
      </Button>

      <Button startIcon={<PlayArrowIcon />} onClick={actions.handleStartScheduler}>
        Start Scheduler
      </Button>

      <Button startIcon={<StopIcon />} onClick={actions.handleStopScheduler}>
        Stop Scheduler
      </Button>

      <Button startIcon={<ListIcon />} onClick={() => actions.fetchJobs().then(() => setJobsOpen(true))}>
        Show Jobs
      </Button>
    </Box>
  );
}
