import React, { useState, useEffect } from 'react';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import {
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  TableFooter,
  TablePagination,
  IconButton,
  Typography,
  Box,
  Button,
  Stack,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Tooltip,
  Chip,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import PingIcon from '@mui/icons-material/Cloud';
import SyncIcon from '@mui/icons-material/Sync';

export default function DevicesTable({
  devices = [],
  branchId = null,
  onFetch,
  onPoll,
  onCreate,
  onUpdate,
  onDelete,
  onBack,
}) {
  const [formOpen, setFormOpen] = useState(false);
  const [formMode, setFormMode] = useState('add');
  const [formData, setFormData] = useState({ name: '', ip_address: '', port: 4370, serial_no: '' });
  const [deleting, setDeleting] = useState({ open: false, id: null, name: '' });
  const [submitting, setSubmitting] = useState(false);

  // pagination
  const [page, setPage] = useState(0);
  const rowsPerPage = 30;

  useEffect(() => {
    if (page > 0 && page * rowsPerPage >= devices.length) setPage(0);
  }, [devices, page]);

  function openAdd() {
    setFormMode('add');
    setFormData({ name: '', ip_address: '', port: 4370, serial_no: '' });
    setFormOpen(true);
  }

  function openEdit(device) {
    setFormMode('edit');
    setFormData({
      id: device.id,
      name: device.name,
      ip_address: device.ip_address,
      port: device.port || 4370,
      serial_no: device.serial_no,
    });
    setFormOpen(true);
  }

  async function submitForm() {
    if (!formData.name.trim()) {
      alert('Name is required');
      return;
    }
    if (!formData.ip_address.trim()) {
      alert('IP Address is required');
      return;
    }

    setSubmitting(true);
    try {
      if (formMode === 'add') {
        if (!branchId) {
          alert('Missing branch context');
          setSubmitting(false);
          return;
        }
        const res = await onCreate(branchId, {
          name: formData.name,
          ip_address: formData.ip_address,
          port: formData.port,
          serial_no: formData.serial_no,
        });
        if (res?.success) setFormOpen(false);
        else alert('Failed to create device');
      } else {
        const res = await onUpdate(formData.id, {
          name: formData.name,
          ip_address: formData.ip_address,
          port: formData.port,
          serial_no: formData.serial_no,
        });
        if (res?.success) setFormOpen(false);
        else alert('Failed to update device');
      }
    } catch (err) {
      console.error(err);
      alert('Error performing request');
    } finally {
      setSubmitting(false);
    }
  }

  async function confirmDelete() {
    setSubmitting(true);
    try {
      const res = await onDelete(deleting.id);
      if (res?.success) setDeleting({ open: false, id: null, name: '' });
      else alert('Failed to delete device');
    } catch (err) {
      console.error(err);
      alert('Error deleting device');
    } finally {
      setSubmitting(false);
    }
  }

  const handleChangePage = (event, newPage) => setPage(newPage);
  const paginated = devices.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);

  return (
    <Box>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          mb: 1,
        }}
      >
        <Button startIcon={<ArrowBackIcon />} onClick={() => onBack && onBack()} size="small">
          Back
        </Button>

        <Typography variant="subtitle1" sx={{ flexGrow: 1, textAlign: 'center' }}>
          {branchId ? `Devices for Branch ${branchId}` : 'All Devices'}
        </Typography>

        <Button startIcon={<AddIcon />} onClick={openAdd} size="small">
          Add Device
        </Button>
      </Box>

      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>
              <Chip label="Name" size="medium" sx={{ backgroundColor: 'black', color: 'white' }} />
            </TableCell>
            <TableCell>
              <Chip label="IP Address" size="medium" sx={{ backgroundColor: 'black', color: 'white' }} />
            </TableCell>
            <TableCell align="center">
              <Chip label="Port" size="medium" sx={{ backgroundColor: 'black', color: 'white' }} />
            </TableCell>
            <TableCell align="center">
              <Chip label="Serial" size="medium" sx={{ backgroundColor: 'black', color: 'white' }} />
            </TableCell>
            <TableCell align="right">
              <Chip label="Actions" size="medium" sx={{ backgroundColor: 'black', color: 'white' }} />
            </TableCell>
          </TableRow>
        </TableHead>

        <TableBody>
          {paginated.map((d) => (
            <TableRow key={d.id} hover>
              <TableCell>
                <Chip label={d.name} size="small" sx={{ backgroundColor: 'deepskyblue', color: 'black' }} />
              </TableCell>
              <TableCell>
                <Chip label={d.ip_address} size="small" sx={{ backgroundColor: 'orange', color: 'black' }} />
              </TableCell>
              <TableCell align="center">
                <Chip label={d.port ?? 4370} size="small" sx={{ backgroundColor: 'yellow', color: 'black' }} />
              </TableCell>
              <TableCell align="center">
                <Chip label={d.serial_no ?? ''} size="small" sx={{ backgroundColor: 'cyan', color: 'black' }} />
              </TableCell>
              <TableCell align="right">
                <Stack direction="row" spacing={1} justifyContent="flex-end">
                  <Tooltip title="Fetch">
                    <span>
                      <IconButton
                        size="small"
                        onClick={() => (onFetch ? onFetch(d.id) : onPoll && onPoll(d.id))}
                        disabled={!onFetch && !onPoll}
                        sx={{
                          color: 'green',
                          '&:hover': { backgroundColor: 'green', color: 'white' },
                        }}
                      >
                        <SyncIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>

                  <Tooltip title="Ping">
                    <span>
                      <IconButton
                        size="small"
                        onClick={() => onPoll && onPoll(d.id)}
                        disabled={!onPoll}
                        sx={{
                          color: 'deepskyblue',
                          '&:hover': { backgroundColor: 'deepskyblue', color: 'white' },
                        }}
                      >
                        <PingIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>

                  <Tooltip title="Edit">
                    <IconButton size="small" onClick={() => openEdit(d)} sx={{ color: 'yellow', '&:hover': { backgroundColor: 'orange', color: 'white' } }}>
                      <EditIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>

                  <Tooltip title="Delete">
                    <IconButton size="small" color="error" onClick={() => setDeleting({ open: true, id: d.id, name: d.name })} sx={{ color: 'red', '&:hover': { backgroundColor: 'red', color: 'white' }}}>
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Stack>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>

        <TableFooter>
          <TableRow>
            <TableCell colSpan={5}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Button
                    size="small"
                    onClick={(e) => handleChangePage(e, Math.max(0, page - 1))}
                    disabled={page === 0}
                  >
                    Previous
                  </Button>
                  <Button
                    size="small"
                    onClick={(e) => handleChangePage(e, Math.min(Math.ceil(devices.length / rowsPerPage) - 1, page + 1))}
                    disabled={page >= Math.ceil(devices.length / rowsPerPage) - 1}
                    sx={{ ml: 1 }}
                  >
                    Next
                  </Button>
                </Box>

                <TablePagination
                  rowsPerPageOptions={[30]}
                  count={devices.length}
                  rowsPerPage={rowsPerPage}
                  page={page}
                  onPageChange={handleChangePage}
                  onRowsPerPageChange={() => {}}
                  labelDisplayedRows={({ from, to, count }) => `${from}-${to} of ${count}`}
                />
              </Box>
            </TableCell>
          </TableRow>
        </TableFooter>
      </Table>

      {/* Form dialog */}
      <Dialog open={formOpen} onClose={() => setFormOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{formMode === 'add' ? 'Add Device' : 'Edit Device'}</DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
            <TextField label="Name" value={formData.name} onChange={(e) => setFormData((s) => ({ ...s, name: e.target.value }))} fullWidth />
            <TextField label="IP Address" value={formData.ip_address} onChange={(e) => setFormData((s) => ({ ...s, ip_address: e.target.value }))} fullWidth />
            <TextField label="Port" value={formData.port} onChange={(e) => setFormData((s) => ({ ...s, port: Number(e.target.value) }))} fullWidth />
            <TextField label="Serial No" value={formData.serial_no} onChange={(e) => setFormData((s) => ({ ...s, serial_no: e.target.value }))} fullWidth />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFormOpen(false)}>Cancel</Button>
          <Button onClick={submitForm} disabled={submitting} variant="contained">
            {formMode === 'add' ? 'Create' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete confirmation */}
      <Dialog open={deleting.open} onClose={() => setDeleting({ open: false, id: null, name: '' })}>
        <DialogTitle>Delete Device</DialogTitle>
        <DialogContent>
          <Typography>Are you sure you want to delete device "{deleting.name}"?</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleting({ open: false, id: null, name: '' })}>Cancel</Button>
          <Button onClick={confirmDelete} color="error" variant="contained" disabled={submitting}>
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
