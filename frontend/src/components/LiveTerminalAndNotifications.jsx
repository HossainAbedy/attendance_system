// src/components/LiveTerminalAndNotifications.jsx
import React, { useEffect, useRef, useState } from 'react';
import { io } from 'socket.io-client';

// Material UI
import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import TextField from '@mui/material/TextField';
import Select from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import DownloadIcon from '@mui/icons-material/Download';
import ClearIcon from '@mui/icons-material/ClearAll';
import PauseIcon from '@mui/icons-material/Pause';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import Badge from '@mui/material/Badge';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import Divider from '@mui/material/Divider';

const MAX_LINES = 2000;

/**
 * Props:
 *  - socketUrl (string) : required (recommended) — socket server URL, e.g. "http://localhost:5000"
 *  - containerWidth (string) : default "30%" — width of the whole widget (use percentage or px)
 *  - notificationsHeight (string) : default "220px"
 *  - terminalHeight (string) : default "420px"
 */
function formatLine(evt) {
  const ts = evt.timestamp || new Date().toISOString();
  const device = evt.device_name || evt.device_id || 'unknown';
  const level = (evt.level || 'info').toUpperCase();
  const msg = evt.message || JSON.stringify(evt);
  const extra = evt.extra && Object.keys(evt.extra).length ? ` ${JSON.stringify(evt.extra)}` : '';
  return `${ts} | ${device} | ${level} | ${msg}${extra}`;
}

function resolveDefaultSocketUrl() {
  // If user didn't pass a socketUrl prop, try a reasonable dev fallback:
  try {
    const { protocol, hostname, port } = window.location;
    if (port === '3000') return `${protocol}//${hostname}:5000`; // dev convenience
  } catch (e) {}
  return window.location.origin;
}

function useSocket(onEvent, socketUrl) {
  const socketRef = useRef(null);

  useEffect(() => {
    if (socketRef.current) return;
    const url = socketUrl || resolveDefaultSocketUrl();
    const s = io(url, { transports: ['websocket', 'polling'] });
    socketRef.current = s;

    s.on('device_status', (payload) => onEvent && onEvent('device_status', payload));
    s.on('new_log', (payload) => onEvent && onEvent('new_log', payload));
    s.on('access_log', (payload) => onEvent && onEvent('access_log', payload));

    s.on('connect', () => onEvent && onEvent('sys', { timestamp: new Date().toISOString(), message: 'socket connected' }));
    s.on('disconnect', () => onEvent && onEvent('sys', { timestamp: new Date().toISOString(), message: 'socket disconnected' }));

    s.on('connect_error', (err) => {
      // surface to app if desired
      onEvent && onEvent('sys', { timestamp: new Date().toISOString(), message: `connect_error: ${err?.message || err}` });
    });

    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
        socketRef.current = null;
      }
    };
  }, [onEvent, socketUrl]);

  return socketRef;
}

function TerminalConsole({ socketUrl, terminalHeight = '420px' }) {
  const [lines, setLines] = useState([]);
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState('ALL');
  const [search, setSearch] = useState('');
  const containerRef = useRef(null);
  const bottomRef = useRef(null);

  const handleEvent = (type, payload) => {
    let evt = null;
    if (type === 'device_status') evt = payload;
    else if (type === 'new_log') evt = {
      timestamp: payload.timestamp || new Date().toISOString(),
      device_name: payload.device_name || `device_${payload.device_id}`,
      level: payload.status || 'new',
      message: `NEW LOG: rid=${payload.rid} user=${payload.user_id}`,
      extra: payload
    };
    else if (type === 'access_log') evt = {
      timestamp: payload.checktime || new Date().toISOString(),
      device_name: payload.userid || 'access',
      level: 'access',
      message: `ACCESS: ${payload.userid}`,
      extra: payload
    };
    else if (type === 'sys') evt = { timestamp: payload.timestamp, device_name: 'system', level: 'info', message: payload.message };

    if (!evt) return;

    const line = formatLine(evt);

    setLines(prev => {
      const next = [...prev, { raw: evt, text: line }];
      if (next.length > MAX_LINES) next.splice(0, next.length - MAX_LINES);
      return next;
    });
  };

  useSocket(handleEvent, socketUrl);

  useEffect(() => {
    if (!paused && containerRef.current) {
      const el = containerRef.current;
      const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50; // threshold
      if (isNearBottom) {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
      }
    }
  }, [lines, paused]);

  const clear = () => setLines([]);
  const download = () => {
    const content = lines.map(l => l.text).join("\n");
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'terminal_output.txt');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const filtered = lines.filter(l => {
    if (filter !== 'ALL' && !l.text.includes(`| ${filter} |`)) return false;
    if (search && !l.text.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <Paper elevation={3} sx={{ p: 1, height: terminalHeight, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
        <Box>
          <Typography variant="subtitle2">Terminal</Typography>
          <Typography variant="caption" color="text.secondary">Realtime logs</Typography>
        </Box>

        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          <TextField size="small" placeholder="search..." value={search} onChange={e => setSearch(e.target.value)} />
          <Select size="small" value={filter} onChange={e => setFilter(e.target.value)}>
            <MenuItem value="ALL">ALL</MenuItem>
            <MenuItem value="DEBUG">DEBUG</MenuItem>
            <MenuItem value="INFO">INFO</MenuItem>
            <MenuItem value="NEW">NEW</MenuItem>
            <MenuItem value="ERROR">ERROR</MenuItem>
            <MenuItem value="ACCESS">ACCESS</MenuItem>
          </Select>
          <IconButton onClick={() => setPaused(p => !p)} color="primary" size="small">
            {paused ? <PlayArrowIcon /> : <PauseIcon />}
          </IconButton>
          <IconButton onClick={clear} color="error" size="small"><ClearIcon /></IconButton>
          <IconButton onClick={download} color="success" size="small"><DownloadIcon /></IconButton>
        </Box>
      </Box>

      <Box
        ref={containerRef}
        sx={{
          flex: 1,
          overflowY: 'auto',
          bgcolor: 'common.black',
          color: 'grey.100',
          fontFamily: 'monospace',
          p: 1,
          borderRadius: 1,
          lineHeight: '1.3',
          fontSize: '0.78rem'
        }}
      >
        {filtered.map((l, i) => (
          <Box
            key={i}
            sx={{
              whiteSpace: 'pre-wrap',
              py: 0.3,
              color: (l.raw.level && l.raw.level.toLowerCase && l.raw.level.toLowerCase() === 'error') ? 'error.main' : 'grey.100'
            }}
          >
            {l.text}
          </Box>
        ))}
        <div ref={bottomRef} />
      </Box>
    </Paper>
  );
}

function NotificationsPanel({ socketUrl, notificationsHeight = '220px' }) {
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);

  const handleEvent = (type, payload) => {
    let note = null;
    if (type === 'access_log') {
      note = {
        id: `access_${payload.userid}_${payload.checktime}`,
        title: `Access: ${payload.userid}`,
        time: payload.checktime || new Date().toISOString(),
        meta: payload,
        read: false
      };
    } else if (type === 'new_log') {
      note = {
        id: `log_${payload.rid}_${payload.timestamp}`,
        title: `New log ${payload.user_id}`,
        time: payload.timestamp || new Date().toISOString(),
        meta: payload,
        read: false
      };
    } else if (type === 'device_status') {
      const level = (payload.level || 'info').toLowerCase();
      note = {
        id: `status_${payload.device_id}_${payload.timestamp}`,
        title: `${payload.device_name} — ${level}`,
        time: payload.timestamp || new Date().toISOString(),
        meta: payload,
        read: level === 'debug'
      };
    } else if (type === 'sys') {
      note = {
        id: `sys_${payload.timestamp}`,
        title: payload.message,
        time: payload.timestamp,
        meta: payload,
        read: false
      };
    }

    if (!note) return;
    setItems(prev => [note, ...prev].slice(0, 200));
    setUnread(u => u + (note.read ? 0 : 1));
  };

  useSocket(handleEvent, socketUrl);

  const markRead = (id) => {
    setItems(prev => prev.map(it => it.id === id ? { ...it, read: true } : it));
    setUnread(items.filter(i => !i.read && i.id !== id).length);
  };
  const markAllRead = () => {
    setItems(prev => prev.map(it => ({ ...it, read: true })));
    setUnread(0);
  };
  const clearAll = () => {
    setItems([]);
    setUnread(0);
  };

  return (
    <Paper elevation={3} sx={{ p: 1, height: notificationsHeight, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
        <Box>
          <Typography variant="subtitle2">Notifications</Typography>
          <Typography variant="caption" color="text.secondary">Realtime activity & alerts</Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          <Badge badgeContent={unread} color="error">
            <Box sx={{ width: 24 }} />
          </Badge>
          <Button size="small" onClick={markAllRead}>Mark all</Button>
          <Button size="small" color="error" onClick={clearAll}>Clear</Button>
        </Box>
      </Box>

      <Box sx={{ overflow: 'auto', flex: 1 }}>
        {items.length === 0 && <Typography variant="body2" color="text.secondary">No notifications yet</Typography>}
        <List dense disablePadding>
          {items.map(it => (
            <React.Fragment key={it.id}>
              <ListItem alignItems="flex-start" secondaryAction={<Button size="small" onClick={() => markRead(it.id)}>Mark</Button>}>
                <ListItemText primary={it.title} secondary={new Date(it.time).toLocaleString()} />
              </ListItem>
              <Divider component="li" />
            </React.Fragment>
          ))}
        </List>
      </Box>
    </Paper>
  );
}

/**
 * Main exported widget.
 * Place this in the right column of your layout. Defaults:
 *   containerWidth = '30%'  (you can pass '400px' or '28%' etc)
 *   notificationsHeight = '220px'
 *   terminalHeight = '420px'
 */
export default function LiveTerminalAndNotifications({
  socketUrl,
  containerWidth = '30%',
  notificationsHeight = '220px',
  terminalHeight = '420px'
}) {
  return (
    <Box sx={{
      width: containerWidth,
      minWidth: '260px',
      display: 'flex',
      flexDirection: 'column',
      gap: 1,
      // keep widget fixed in height so it doesn't overflow page layout
      maxHeight: '92vh',
      overflow: 'hidden',
      p: 1
    }}>
      {/* Notifications above terminal */}
      <NotificationsPanel socketUrl={socketUrl} notificationsHeight={notificationsHeight} />
      <TerminalConsole socketUrl={socketUrl} terminalHeight={terminalHeight} />
    </Box>
  );
}
