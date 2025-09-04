// FILE: src/components/SyncControls.jsx
import React, { useState, useRef, useEffect } from "react";
import { triggerExportToEnddb, getJobStatus } from "../api";
import {
  Stack,
  Box,
  Button,
  Tooltip,
  CircularProgress,
  Snackbar,
  Alert,
} from "@mui/material";
import SyncIcon from "@mui/icons-material/Sync";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import StopIcon from "@mui/icons-material/Stop";
import ListIcon from "@mui/icons-material/List";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";

export default function SyncControls({ actions = {} }) {
  const {
    handleTotalSync = () => {},
    handleStartScheduler = () => {},
    handleStopScheduler = () => {},
    fetchJobs = () => {},
    handleExportEnddb = null, // if provided, call this instead of internal API
    isSyncing = false,
    isStarting = false,
    isStopping = false,
    isLoadingJobs = false,
    isExporting: externalIsExporting = false,
  } = actions;

  // Local export state
  const [isExporting, setIsExporting] = useState(false || externalIsExporting);
  const [snack, setSnack] = useState({
    open: false,
    severity: "info",
    message: "",
  });

  // Polling refs so we can cancel
  const pollIntervalRef = useRef(null);
  const pollAttemptsRef = useRef(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };
  }, []);

  const btnBase = {
    px: 3,
    py: 1.2,
    borderRadius: 2,
    textTransform: "none",
    fontWeight: 700,
    minWidth: 170,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
  };

  const closeSnack = () => setSnack((s) => ({ ...s, open: false }));

  async function internalExportHandler() {
    // If user provided a custom handler, call it and don't do default behaviour
    if (typeof handleExportEnddb === "function") {
      try {
        setIsExporting(true);
        await handleExportEnddb();
      } catch (e) {
        setSnack({ open: true, severity: "error", message: `Export error: ${e?.message || e}` });
      } finally {
        setIsExporting(false);
      }
      return;
    }

    setIsExporting(true);
    setSnack({ open: true, severity: "info", message: "Starting export..." });

    try {
      // trigger export (POST)
      const res = await triggerExportToEnddb({}); // can pass lookback_days, timeout via opts
      const data = res?.data;

      // Backend might return either immediate result (result) or a job id
      if (data && data.job_id) {
        const jobId = data.job_id;
        setSnack({
          open: true,
          severity: "info",
          message: `Export job started (job_id=${jobId}). Waiting for completion...`,
        });

        // start polling job status
        pollAttemptsRef.current = 0;
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }

        pollIntervalRef.current = setInterval(async () => {
          pollAttemptsRef.current += 1;
          // safety: stop polling after 90 attempts (~3 minutes @ 2s)
          if (pollAttemptsRef.current > 90) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
            if (mountedRef.current) {
              setIsExporting(false);
              setSnack({
                open: true,
                severity: "warning",
                message: `Export job ${jobId} timed out (no final status).`,
              });
            }
            return;
          }

          try {
            const st = await getJobStatus(jobId);
            const job = st?.data || st; // depending on your api wrapper shape
            if (!job) {
              // continue polling
              return;
            }
            // job.status might be 'running', 'finished', 'failed'
            if (job.status === "finished" || job.status === "failed") {
              // stop polling
              clearInterval(pollIntervalRef.current);
              pollIntervalRef.current = null;

              // job.results is an array; exporter pushed result dict there (first element)
              const result = (job.results && job.results.length && job.results[0]) || job.results || null;

              if (job.status === "finished") {
                // If result is an object with exported counts prefer to show them
                if (result && typeof result === "object" && ("exported" in result || "inserted" in result)) {
                  const exported = result.exported ?? result.inserted ?? 0;
                  const skipped = result.skipped_existing ?? result.skipped_existing ?? 0;
                  const errors = result.errors ?? 0;
                  setSnack({
                    open: true,
                    severity: errors ? "warning" : "success",
                    message: `Export finished: exported=${exported} skipped=${skipped} errors=${errors}`,
                  });
                } else {
                  setSnack({
                    open: true,
                    severity: "success",
                    message: `Export job ${jobId} finished.`,
                  });
                }
              } else {
                setSnack({
                  open: true,
                  severity: "error",
                  message: `Export job ${jobId} failed. Check server logs.`,
                });
              }

              if (mountedRef.current) {
                setIsExporting(false);
              }
            }
          } catch (e) {
            // if transient error, continue polling; after many attempts, will timeout
            console.error("Poll job status error:", e);
          }
        }, 2000);

        return;
      }

      // Some backends return immediate result object
      if (data && data.result) {
        const r = data.result;
        const exported = r.exported ?? r.inserted ?? 0;
        const skipped = r.skipped_existing ?? 0;
        const errors = r.errors ?? 0;
        setSnack({
          open: true,
          severity: errors ? "warning" : "success",
          message: `Export done: exported=${exported} skipped=${skipped} errors=${errors}`,
        });
      } else {
        // fallback success message
        setSnack({ open: true, severity: "success", message: "Export request completed." });
      }
    } catch (err) {
      console.error("Export API error:", err);
      const msg = err?.response?.data?.error || err?.message || String(err);
      setSnack({ open: true, severity: "error", message: `Export failed: ${msg}` });
    } finally {
      // If a job_id was returned we leave isExporting true until polling completes.
      // Only clear exporting if there is no background job.
      if (!pollIntervalRef.current) {
        setIsExporting(false);
      }
    }
  }

  return (
    <>
      <Box sx={{ display: "flex", justifyContent: "center", mt: 3 }}>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={2}
          alignItems="center"
          justifyContent="center"
          sx={{ flexWrap: "wrap" }}
        >
          {/* Start Scheduler */}
          <Tooltip title="Start recurring scheduler">
            <span>
              <Button
                variant="contained"
                onClick={handleStartScheduler}
                startIcon={<PlayArrowIcon />}
                disabled={isStarting}
                aria-label="Start scheduler"
                aria-busy={isStarting ? "true" : "false"}
                sx={{
                  ...btnBase,
                  boxShadow: "0 8px 20px rgba(56,142,60,0.25)",
                  background: "linear-gradient(90deg, #66BB6A 0%, #2E7D32 100%)",
                  color: "common.white",
                  "&:hover": {
                    background: "linear-gradient(90deg, #81C784 0%, #1B5E20 100%)",
                    boxShadow: "0 10px 26px rgba(46,125,50,0.35)",
                  },
                }}
              >
                {isStarting && <CircularProgress size={18} color="inherit" sx={{ mr: 1 }} />}
                Start 
              </Button>
            </span>
          </Tooltip>

          {/* Stop Scheduler */}
          <Tooltip title="Stop recurring scheduler">
            <span>
              <Button
                variant="contained"
                onClick={handleStopScheduler}
                startIcon={<StopIcon />}
                disabled={isStopping}
                aria-label="Stop scheduler"
                aria-busy={isStopping ? "true" : "false"}
                sx={{
                  ...btnBase,
                  boxShadow: "0 8px 20px rgba(244,67,54,0.25)",
                  background: "linear-gradient(90deg, #FF7043 0%, #D32F2F 100%)",
                  color: "common.white",
                  "&:hover": {
                    background: "linear-gradient(90deg, #FF8A65 0%, #B71C1C 100%)",
                    boxShadow: "0 10px 26px rgba(211,47,47,0.35)",
                  },
                }}
              >
                {isStopping && <CircularProgress size={18} color="inherit" sx={{ mr: 1 }} />}
                Stop 
              </Button>
            </span>
          </Tooltip>

          {/* Full Sync */}
          <Tooltip title="Fetch logs from all branches now">
            <span>
              <Button
                onClick={handleTotalSync}
                startIcon={<SyncIcon />}
                disabled={isSyncing}
                aria-label="Full sync"
                aria-busy={isSyncing ? "true" : "false"}
                sx={{
                  ...btnBase,
                  boxShadow: "0 8px 20px rgba(25,118,210,0.12)",
                  background: "linear-gradient(90deg,#00bfa5 0%,#1976d2 100%)",
                  color: "common.white",
                  "&:hover": {
                    background: "linear-gradient(90deg,#00d7b0 0%,#115293 100%)",
                    boxShadow: "0 10px 26px rgba(25,118,210,0.16)",
                  },
                }}
              >
                {isSyncing && <CircularProgress size={18} color="inherit" sx={{ mr: 1 }} />}
                 Sync 
              </Button>
            </span>
          </Tooltip>

          {/* Export EndDB */}
          <Tooltip title="Export attendance logs to EndDB">
            <span>
              <Button
                onClick={internalExportHandler}
                startIcon={<CloudUploadIcon />}
                disabled={isExporting}
                aria-label="Export EndDB"
                aria-busy={isExporting ? "true" : "false"}
                sx={{
                  ...btnBase,
                  boxShadow: "0 8px 20px rgba(156,39,176,0.25)",
                  background: "linear-gradient(90deg, #AB47BC 0%, #6A1B9A 100%)",
                  color: "common.white",
                  "&:hover": {
                    background: "linear-gradient(90deg, #BA68C8 0%, #4A148C 100%)",
                    boxShadow: "0 10px 26px rgba(123,31,162,0.35)",
                  },
                }}
              >
                {isExporting && <CircularProgress size={18} color="inherit" sx={{ mr: 1 }} />}
                Export 
              </Button>
            </span>
          </Tooltip>

          {/* View Jobs */}
          <Tooltip title="See recent sync jobs">
            <span>
              <Button
                onClick={fetchJobs}
                startIcon={<ListIcon />}
                disabled={isLoadingJobs}
                aria-label="View jobs"
                aria-busy={isLoadingJobs ? "true" : "false"}
                sx={{
                  ...btnBase,
                  boxShadow: "0 8px 20px rgba(255,183,77,0.25)",
                  background: "linear-gradient(90deg, #FFD54F 0%, #FF9800 100%)",
                  color: "common.white",
                  "&:hover": {
                    background: "linear-gradient(90deg, #FFE082 0%, #FB8C00 100%)",
                    boxShadow: "0 10px 26px rgba(255,152,0,0.35)",
                  },
                }}
              >
                {isLoadingJobs && <CircularProgress size={18} color="inherit" sx={{ mr: 1 }} />}
                 Jobs
              </Button>
            </span>
          </Tooltip>
        </Stack>
      </Box>

      <Snackbar
        open={snack.open}
        autoHideDuration={6000}
        onClose={closeSnack}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
      >
        <Alert onClose={closeSnack} severity={snack.severity} sx={{ width: "100%" }}>
          {snack.message}
        </Alert>
      </Snackbar>
    </>
  );
}
