import React from 'react';
import { Avatar } from '@mui/material';
import CloudQueueIcon from '@mui/icons-material/CloudQueue';
import CloudOffIcon from '@mui/icons-material/CloudOff';

export default function StatusDot({ online }) {
  return (
    <Avatar sx={{ width: 28, height: 28, bgcolor: online ? 'success.main' : 'grey.500' }}>
      {online ? <CloudQueueIcon /> : <CloudOffIcon />}
    </Avatar>
  );
}