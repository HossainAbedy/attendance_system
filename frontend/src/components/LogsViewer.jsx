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

function dtLocalToISO(val) {
  if (!val) return null;
  const dt = new Date(val);
  if (isNaN(dt.getTime())) return null;
  return dt.toISOString();
}

function statusColor(s) {
  if (!s) return "rgba(6,95,70,0.08)"; // neutral
  const low = String(s).toLowerCase();
  if (low.includes("error") || low.includes("fail") || low.includes("denied") || low.includes("unauth")) return "rgba(255,59,48,0.12)";
  if (low.includes("ok") || low.includes("success") || low.includes("passed") || low.includes("accepted")) return "rgba(16,185,129,0.12)";
  return "rgba(6,95,70,0.08)";
}

export default function LogsViewer({ branchId = null, deviceId = null, onBack = () => {} }) {
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState([]);
  const [error, setError] = useState(null);

  const [page, setPage] = useState(0);
  const [perPage, setPerPage] = useState(25);
  const [total, setTotal] = useState(0);

  const [q, setQ] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [sortDir, setSortDir] = useState("desc");
  const [refreshKey, setRefreshKey] = useState(0);

  const [filters, setFilters] = useState({
    timestamp_from: "",
    timestamp_to: "",
    user_id: "",
    record_id: "",
    device: "",
    status: "",
  });

  const buildParams = useCallback(() => {
    const params = {
      page: page + 1,
      per_page: perPage,
      sort_by: "timestamp",
      sort_dir: sortDir,
    };
    if (q && q.length) params.q = q;
    if (branchId) params.branch_id = branchId;
    if (deviceId) params.device_id = deviceId;

    const tsFrom = dtLocalToISO(filters.timestamp_from);
    const tsTo = dtLocalToISO(filters.timestamp_to);
    if (tsFrom) params.timestamp_from = tsFrom;
    if (tsTo) params.timestamp_to = tsTo;

    if (filters.user_id) params.user_id = filters.user_id;
    if (filters.record_id) params.record_id = filters.record_id;
    if (filters.device) params.device = filters.device;
    if (filters.status) params.status = filters.status;

    return params;
  }, [page, perPage, q, sortDir, branchId, deviceId, filters]);

  useEffect(() => {
    let mounted = true;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const params = buildParams();
        const res = deviceId ? await getLogsByDevice(deviceId, params) : await getLogs(params);
        const fetchedItems = Array.isArray(res.data.items) ? res.data.items : [];
        if (!mounted) return;
        setItems(fetchedItems);
        setTotal(typeof res.data.total === "number" ? res.data.total : fetchedItems.length);
      } catch (err) {
        if (!mounted) return;
        setError(err.message || "Failed to load logs");
      } finally {
        if (mounted) setLoading(false);
      }
    }
    load();
    return () => { mounted = false; };
  }, [deviceId, buildParams, refreshKey]);

  function handleSearchKeyDown(e) {
    if (e.key === "Enter") {
      setQ(searchInput.trim());
      setPage(0);
    }
  }

  function handleClearSearch() {
    setSearchInput("");
    setQ("");
    setPage(0);
    setFilters({
      timestamp_from: "",
      timestamp_to: "",
      user_id: "",
      record_id: "",
      device: "",
      status: "",
    });
  }

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

  function handleRefresh() {
    setRefreshKey((k) => k + 1);
  }

  function handleFilterChange(field, value) {
    setFilters((f) => ({ ...f, [field]: value }));
  }

  function handleApplyFilters() {
    setQ(searchInput.trim());
    setPage(0);
    setRefreshKey((k) => k + 1);
  }

  function handleClearFilters() {
    setFilters({
      timestamp_from: "",
      timestamp_to: "",
      user_id: "",
      record_id: "",
      device: "",
      status: "",
    });
    setPage(0);
    setRefreshKey((k) => k + 1);
  }

  const paginatedItems = items; // backend already paginates

  return (
    <Paper sx={{ borderRadius: 2, boxShadow: '0 10px 30px rgba(2,6,23,0.06)', overflow: 'hidden' }}>
      {/* Header */}
      <Box sx={{ px: 2, py: 1.25, background: 'linear-gradient(90deg,#0ea5a4 0%,#2563eb 100%)', color: '#fff' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Box>
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
              {deviceId ? `Logs — Device ${deviceId}` : branchId ? `Logs — Branch ${branchId}` : "Logs"}
            </Typography>
            <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.9)' }}>
              {loading ? "Loading..." : `${total} entries — page ${page + 1}`}
            </Typography>
          </Box>

          <Stack direction="row" spacing={1} alignItems="center">
            <Tooltip title="Back">
              <IconButton onClick={onBack} size="small" sx={{ color: '#fff' }}>
                <ArrowBackIcon />
              </IconButton>
            </Tooltip>

            <TextField
              size="small"
              placeholder="Search (global)"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={handleSearchKeyDown}
              sx={{ bgcolor: 'rgba(255,255,255,0.08)', borderRadius: 1, input: { color: '#fff' } }}
              InputProps={{ sx: { color: '#fff' } }}
            />

            <FormControl size="small" sx={{ minWidth: 90 }}>
              <InputLabel id="rows-label" sx={{ color: 'rgba(255,255,255,0.9)' }}>Rows</InputLabel>
              <Select
                labelId="rows-label"
                value={perPage}
                label="Rows"
                onChange={handleChangeRowsPerPage}
                sx={{ color: '#fff' }}
              >
                <MenuItem value={10}>10</MenuItem>
                <MenuItem value={25}>25</MenuItem>
                <MenuItem value={50}>50</MenuItem>
                <MenuItem value={100}>100</MenuItem>
              </Select>
            </FormControl>

            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel id="sort-label" sx={{ color: 'rgba(255,255,255,0.9)' }}>Sort</InputLabel>
              <Select labelId="sort-label" value={sortDir} label="Sort" onChange={handleSortChange} sx={{ color: '#fff' }}>
                <MenuItem value="desc">Time ↓</MenuItem>
                <MenuItem value="asc">Time ↑</MenuItem>
              </Select>
            </FormControl>

            <Button
              variant="outlined"
              size="small"
              startIcon={<FilterListIcon />}
              onClick={handleApplyFilters}
              sx={{ color: '#fff', borderColor: 'rgba(255,255,255,0.12)', textTransform: 'none' }}
            >
              Apply
            </Button>

            <Button variant="outlined" size="small" onClick={handleClearFilters} sx={{ color: '#fff', borderColor: 'rgba(255,255,255,0.08)', textTransform: 'none' }}>
              Clear
            </Button>

            <Button variant="contained" size="small" startIcon={<RefreshIcon />} onClick={handleRefresh} sx={{ textTransform: 'none' }}>
              Refresh
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
            <Typography color="error">Error loading logs: {error}</Typography>
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

                  {/* filters row */}
                  <TableRow>
                    <TableCell>
                      <Stack direction="column" spacing={1}>
                        <TextField
                          size="small"
                          type="datetime-local"
                          label="From"
                          value={filters.timestamp_from}
                          onChange={(e) => handleFilterChange("timestamp_from", e.target.value)}
                          InputLabelProps={{ shrink: true }}
                        />
                        <TextField
                          size="small"
                          type="datetime-local"
                          label="To"
                          value={filters.timestamp_to}
                          onChange={(e) => handleFilterChange("timestamp_to", e.target.value)}
                          InputLabelProps={{ shrink: true }}
                        />
                      </Stack>
                    </TableCell>

                    <TableCell>
                      <TextField
                        size="small"
                        placeholder="User ID"
                        value={filters.user_id}
                        onChange={(e) => handleFilterChange("user_id", e.target.value)}
                      />
                    </TableCell>

                    <TableCell>
                      <TextField
                        size="small"
                        placeholder="Record ID"
                        value={filters.record_id}
                        onChange={(e) => handleFilterChange("record_id", e.target.value)}
                      />
                    </TableCell>

                    <TableCell>
                      <TextField
                        size="small"
                        placeholder="Device"
                        value={filters.device}
                        onChange={(e) => handleFilterChange("device", e.target.value)}
                      />
                    </TableCell>

                    <TableCell>
                      <TextField
                        size="small"
                        placeholder="Status"
                        value={filters.status}
                        onChange={(e) => handleFilterChange("status", e.target.value)}
                      />
                    </TableCell>
                  </TableRow>
                </TableHead>

                <TableBody>
                  {paginatedItems.map((l) => {
                    const ts = l.timestamp ?? l.ts ?? l.time;
                    const user = l.user_id ?? l.user ?? "-";
                    const record = l.record_id ?? l.record ?? "-";
                    const deviceName = (l.device && (l.device.name ?? l.device.id)) || l.device_name || l.device_id || "-";
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
