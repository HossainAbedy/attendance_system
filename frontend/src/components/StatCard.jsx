// FILE: src/components/StatCard.jsx
import React from 'react';
import { Card, CardContent, Box, Typography } from '@mui/material';

export default function StatCard({ title, value, onClick, icon, bgColor }) {
  return (
    <Card
      sx={{
        cursor: onClick ? 'pointer' : 'default',
        backgroundColor: bgColor || 'background.paper',
        color: bgColor ? 'white' : 'inherit'
      }}
      onClick={onClick}
    >
      <CardContent>
        <Box display="flex" alignItems="center" justifyContent="space-between">
          <div>
            <Typography variant="subtitle2" color="inherit">
              {title}
            </Typography>
            <Typography variant="h5" color="inherit">
              {value ?? '-'}
            </Typography>
          </div>
          <Box>{icon}</Box>
        </Box>
      </CardContent>
    </Card>
  );
}
