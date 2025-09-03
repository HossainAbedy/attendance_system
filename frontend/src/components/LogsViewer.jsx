// FILE: src/components/LogsViewer.jsx
import React, { useEffect, useState, useCallback } from "react";
import {
  Box,
  Typography,
  CircularProgress,
  IconButton,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  Paper,
  TextField,
  TableFooter,
  TablePagination,
  Select,
  MenuItem,
  InputLabel,
  FormControl,
  Stack,
  Button,
  Chip,
  TableContainer,
  Tooltip,
} from "@mui/material";
import CheckIcon from '@mui/icons-material/Check';
import ClearIcon from '@mui/icons-material/Clear';
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import RefreshIcon from "@mui/icons-material/Refresh";
import FilterListIcon from "@mui/icons-material/FilterList";
import { getLogs, getLogsByDevice } from "../api";

function formatDate(iso) {
  if (!iso) return "-";
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

// Convert local datetime-local / date values into ISO string (UTC)
function dtLocalToISO(val, endOfDay = false) {
  if (!val) return null;
  let normalized = val;

  // plain date like "2025-08-14"
  if (/^\d{4}-\d{2}-\d{2}$/.test(val)) {
    normalized = endOfDay ? `${val}T23:59:59.999` : `${val}T00:00:00.000`;
  }
  // datetime-local without seconds "YYYY-MM-DDTHH:MM"
  else if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(val)) {
    normalized = endOfDay ? `${val}:59.999` : `${val}:00.000`;
  }
  // otherwise assume it's already a full datetime string

  const dt = new Date(normalized); // interprets normalized as local time
  if (isNaN(dt.getTime())) return null;

  return dt.toISOString();
}

function statusColor(s) {
  if (!s) return "rgba(6,95,70,0.08)"; // neutral
  const low = String(s).toLowerCase();
  if (low.includes("error") || low.includes("fail") || low.includes("denied") || low.includes("unauth"))
    return "rgba(255,59,48,0.12)";
  if (low.includes("ok") || low.includes("success") || low.includes("passed") || low.includes("accepted"))
    return "rgba(16,185,129,0.12)";
  return "rgba(6,95,70,0.08)";
}

export default function LogsViewer({ branchId = null, deviceId = null, onBack = () => {} }) {
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState([]);
  const [error, setError] = useState(null);

  const [page, setPage] = useState(0);
  const [perPage, setPerPage] = useState(25);
  const [total, setTotal] = useState(0);

  const [sortDir, setSortDir] = useState("desc");
  const [refreshKey, setRefreshKey] = useState(0);

  const [filters, setFilters] = useState({
    timestamp_from: "",
    timestamp_to: "",
    user_id: "",
    record_id: "",
    device: "",
    status: "",
    branch: "",
  });

  // Build params for backend request
  const buildParamsForRequest = useCallback(() => {
    const params = {
      page: page + 1,
      per_page: perPage,
      sort_by: "timestamp",
      sort_dir: sortDir,
    };

    if (branchId) params.branch_id = branchId;
    else if (filters.branch) params.branch_id = parseInt(filters.branch, 10);

    const tsFrom = dtLocalToISO(filters.timestamp_from, false);
    const tsTo = dtLocalToISO(filters.timestamp_to, true);

    if (tsFrom) params.from = tsFrom; // backend expects 'from'
    if (tsTo) params.to = tsTo;

    if (filters.user_id) params.user_id = filters.user_id;
    if (filters.record_id) params.record_id = filters.record_id;
    if (filters.device) params.device_id = filters.device;
    if (filters.status) params.status = filters.status;

    return params;
  }, [page, perPage, sortDir, branchId, filters]);

  // Fetch logs when dependencies change
  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError(null);

    const fetchLogs = async () => {
      try {
        const params = buildParamsForRequest();
        const res = deviceId ? await getLogsByDevice(deviceId, params) : await getLogs(params);
        if (!mounted) return;

        // axios response -> data
        const data = res.data || {};
        setItems(Array.isArray(data.items) ? data.items : []);
        setTotal(typeof data.total === "number" ? data.total : (data.total ? Number(data.total) : 0));
      } catch (err) {
        if (!mounted) return;
        setError(err?.response?.data?.message || err.message || "Failed to load logs");
        setItems([]);
        setTotal(0);
      } finally {
        if (mounted) setLoading(false);
      }
    };

    fetchLogs();

    return () => { mounted = false; };
  }, [deviceId, page, perPage, sortDir, refreshKey, branchId, filters, buildParamsForRequest]);

  function handleChangePage(_e, newPage) {
    setPage(newPage);
  }

  function handleChangeRowsPerPage(e) {
    const v = parseInt(e.target.value, 10);
    setPerPage(v);
    setPage(0);
  }

  function handleSortChange(e) {
    setSortDir(e.target.value);
    setPage(0);
  }

  function handleFilterChange(field, value) {
    setFilters((f) => ({ ...f, [field]: value }));
  }

  // Apply filters: reset page and reload
  function handleApplyFilters() {
    setPage(0);
    setRefreshKey(k => k + 1);
  }

  function handleClearFilters() {
    setFilters({
      timestamp_from: "",
      timestamp_to: "",
      user_id: "",
      record_id: "",
      device: "",
      status: "",
      branch: "",
    });
    setPage(0);
    setRefreshKey(k => k + 1);
  }

  function handleRefresh() {
    setRefreshKey(k => k + 1);
  }

  const paginatedItems = items; // backend provides paging

  function handleKeyDownApply(e) {
    if (e.key === "Enter") {
      handleApplyFilters();
    }
  }

  return (
    <Paper sx={{ borderRadius: 2, boxShadow: '0 10px 30px rgba(2,6,23,0.06)', overflow: 'hidden' }}>
      {/* Header */}
      <Box sx={{ px: 2, py: 1.25, background: 'linear-gradient(90deg,#0ea5a4 0%,#2563eb 100%)', color: '#fff' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Tooltip title="Back">
            <IconButton onClick={onBack} size="small" sx={{ color: '#fff' }} aria-label="Back">
              <ArrowBackIcon />
            </IconButton>
          </Tooltip>
          <Box>
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
              {deviceId ? `Logs — Device ${deviceId}` : branchId ? `Logs — Branch ${branchId}` : "Logs"}
            </Typography>
            <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.9)' }}>
              {loading ? "Loading..." : `${total} entries — page ${page + 1}`}
            </Typography>
          </Box>

          {/* Filters / Controls */}
          <Stack direction="row" spacing={1} alignItems="center">
            <TextField
              size="small"
              type="datetime-local"
              label="From"
              value={filters.timestamp_from}
              onChange={(e) => handleFilterChange("timestamp_from", e.target.value)}
              onKeyDown={handleKeyDownApply}
              InputLabelProps={{ shrink: true }}
              sx={{ bgcolor: 'rgba(255,255,255,0.08)', borderRadius: 1 }}
              InputProps={{ sx: { color: '#fff' } }}
            />

            <TextField
              size="small"
              type="datetime-local"
              label="To"
              value={filters.timestamp_to}
              onChange={(e) => handleFilterChange("timestamp_to", e.target.value)}
              onKeyDown={handleKeyDownApply}
              InputLabelProps={{ shrink: true }}
              sx={{ bgcolor: 'rgba(255,255,255,0.08)', borderRadius: 1 }}
              InputProps={{ sx: { color: '#fff' } }}
            />

            <TextField
              size="small"
              placeholder="User ID / Badge"
              value={filters.user_id}
              onChange={(e) => handleFilterChange("user_id", e.target.value)}
              onKeyDown={handleKeyDownApply}
              sx={{ bgcolor: 'rgba(255,255,255,0.08)', borderRadius: 1, input: { color: '#fff' } }}
              InputProps={{ sx: { color: '#fff' } }}
            />

            <TextField
              size="small"
              placeholder="Branch"
              value={filters.branch}
              onChange={(e) => handleFilterChange("branch", e.target.value)}
              onKeyDown={handleKeyDownApply}
              sx={{ bgcolor: 'rgba(255,255,255,0.08)', borderRadius: 1, input: { color: '#fff' } }}
              InputProps={{ sx: { color: '#fff' } }}
            />
        
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel id="sort-label" sx={{ color: 'rgba(255,255,255,0.9)' }}>Sort</InputLabel>
              <Select labelId="sort-label" value={sortDir} label="Sort" onChange={handleSortChange} sx={{ color: '#fff' }}>
                <MenuItem value="desc">Time ↓</MenuItem>
                <MenuItem value="asc">Time ↑</MenuItem>
              </Select>
            </FormControl>

            <Button
              variant="contained"
              size="small"
              startIcon={<FilterListIcon />}
              onClick={handleApplyFilters}
              sx={{ textTransform: 'none' }}
              aria-label="Apply filters"
            >
              
            </Button>

            <Button
              variant="contained"
              size="small"
              startIcon={<ClearIcon />}
              onClick={handleClearFilters}
              sx={{ textTransform: 'none' }}
              aria-label="Clear filters"
            >
        
            </Button>

            <Button
              variant="contained"
              size="small"
              startIcon={<RefreshIcon />}
              onClick={handleRefresh}
              sx={{ textTransform: 'none' }}
              aria-label="Refresh"
            >

            </Button>
          </Stack>
        </Box>
      </Box>

      {/* Body */}
      <Box sx={{ p: 2 }}>
        {loading ? (
          <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
            <CircularProgress />
          </Box>
        ) : error ? (
          <Box sx={{ p: 2 }}>
            <Typography color="error">Error loading logs: {String(error)}</Typography>
          </Box>
        ) : paginatedItems.length === 0 ? (
          <Box sx={{ p: 2 }}>
            <Typography>No logs available.</Typography>
          </Box>
        ) : (
          <>
            <TableContainer component={Paper} sx={{ boxShadow: 'none' }}>
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 700 }}>Time</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>User ID</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>Record ID</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>Device</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>Status</TableCell>
                  </TableRow>
                </TableHead>

                <TableBody>
                  {paginatedItems.map((l) => {
                    const ts = l.timestamp ?? l.ts ?? l.time;
                    const user = l.user_id ?? l.device_userid ?? l.user ?? "-";
                    const record = l.record_id ?? l.record ?? "-";
                    const deviceName = (l.device && (l.device.name ?? l.device.id)) || l.device_name || l.access_device || l.device_id || "-";
                    const status = l.status ?? l.level ?? "-";

                    return (
                      <TableRow key={l.id ?? `${ts}-${Math.random()}`} hover>
                        <TableCell sx={{ whiteSpace: "nowrap" }}>
                          <Chip label={formatDate(ts)} size="small" sx={{ backgroundColor: 'rgba(14,165,233,0.08)', color: 'info.main' }} />
                        </TableCell>

                        <TableCell>
                          <Chip label={user} size="small" sx={{ backgroundColor: 'rgba(59,130,246,0.08)', color: 'primary.main' }} />
                        </TableCell>

                        <TableCell>
                          <Chip label={record} size="small" sx={{ backgroundColor: 'rgba(249,115,22,0.08)', color: 'warning.main' }} />
                        </TableCell>

                        <TableCell>
                          <Chip label={deviceName} size="small" sx={{ backgroundColor: 'rgba(245,158,11,0.06)', color: 'text.primary' }} />
                        </TableCell>

                        <TableCell>
                          <Chip label={String(status)} size="small" sx={{ backgroundColor: statusColor(status), color: 'text.primary', fontWeight: 700 }} />
                        </TableCell>
                      </TableRow>
                    );
                  })}
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
                            onClick={(e) => handleChangePage(e, Math.min(Math.ceil(total / perPage) - 1, page + 1))}
                            disabled={page >= Math.ceil(total / perPage) - 1}
                            sx={{ ml: 1 }}
                          >
                            Next
                          </Button>
                        </Box>

                        <TablePagination
                          rowsPerPageOptions={[10, 25, 50, 100]}
                          count={total}
                          rowsPerPage={perPage}
                          page={page}
                          onPageChange={handleChangePage}
                          onRowsPerPageChange={handleChangeRowsPerPage}
                          labelDisplayedRows={({ from, to, count }) => `${from}-${to} of ${count}`}
                        />
                      </Box>
                    </TableCell>
                  </TableRow>
                </TableFooter>
              </Table>
            </TableContainer>
          </>
        )}
      </Box>
    </Paper>
  );
}
