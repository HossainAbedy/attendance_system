// FILE: src/components/DetailsDialog.jsx
import React from 'react';
import { Dialog, DialogTitle, DialogContent, DialogActions, Button, CircularProgress, Typography } from '@mui/material';
import DevicesTable from './DevicesTable';
import BranchesTable from './BranchesTable';

export default function DetailsDialog({ dialog, onClose, onPoll }) {
  const { open, type, props } = dialog || { open: false };

  return (
    <Dialog open={!!open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle>
        {type === 'branches' && 'Branches'}
        {type === 'devices' && `Devices (Branch ${props?.branchId ?? ''})`}
        {type === 'info' && props?.title}
      </DialogTitle>
      <DialogContent dividers>
        {type === 'branches' && (
          <BranchesTable
            branches={props?.branchesData ?? []}
            onFetch={props?.onFetch}
            onShowDevices={props?.onShowDevices}
            onCreate={props?.onCreate}
            onUpdate={props?.onUpdate}
            onDelete={props?.onDelete}
          />
        )}

        {type === 'devices' && (
          <>
            {props?.loading ? (
              <div style={{ display: 'flex', justifyContent: 'center', padding: 16 }}>
                <CircularProgress />
              </div>
            ) : props?.error ? (
              <Typography>Failed to load devices</Typography>
            ) : (
              <DevicesTable
                branchId={props?.branchId}
                devices={props?.devices ?? []}
                onPoll={onPoll}
                onCreate={props?.onCreate}
                onUpdate={props?.onUpdate}
                onDelete={props?.onDelete}
              />
            )}
          </>
        )}

        {type === 'info' && props?.content}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
