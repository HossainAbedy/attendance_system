// FILE: src/components/BottomBar.jsx

import {
  AppBar,
  Toolbar,
 
} from '@mui/material';


export default function BottomBar() {
  return (
    <AppBar position="static" elevation={6} sx={{ background: 'linear-gradient(90deg,#0f172a 0%,#0ea5a4 100%)' }}>
      <Toolbar sx={{ minHeight: 64 }}>
        
      </Toolbar>
    </AppBar>
  );
}
