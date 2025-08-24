// src/components/StatCard.jsx
import React from "react";
import { Card, CardContent, Typography, Box } from "@mui/material";

/**
 * StatCard
 * Props:
 *  - title
 *  - value
 *  - icon (React element)
 *  - onClick
 *  - gradient (string) OR bgColor (string) - either accepted
 *  - sx (object) - additional styles for Card root
 */
export default function StatCard({
  title = "",
  value = "-",
  icon = null,
  onClick = undefined,
  gradient = undefined,
  bgColor = undefined,
  sx = {},
}) {
  // prefer explicit gradient prop, then bgColor (legacy), then default
  const bg = gradient ?? bgColor ?? "linear-gradient(135deg,#667eea 0%,#764ba2 100%)";

  // safe clone for icon to merge sx
  const renderIcon = () => {
    if (!icon) return null;
    const existingSx = icon.props?.sx ?? {};
    const mergedSx = { ...existingSx, color: "#fff", fontSize: 28 };
    return React.cloneElement(icon, { sx: mergedSx });
  };

  return (
    <Card
      onClick={onClick}
      sx={{
        cursor: onClick ? "pointer" : "default",
        borderRadius: 2,
        overflow: "hidden",
        boxShadow: "0 6px 18px rgba(15,23,42,0.06)",
        transition: "transform .12s ease, box-shadow .12s ease",
        "&:hover": onClick
          ? {
              transform: "translateY(-6px)",
              boxShadow: "0 14px 36px rgba(15,23,42,0.12)",
            }
          : {},
        ...sx,
      }}
    >
      {/* inner box gets the gradient background */}
      <Box sx={{ background: bg, p: 2 }}>
        <CardContent sx={{ p: 0 }}>
          <Box display="flex" alignItems="center" justifyContent="space-between">
            <Box>
              <Typography variant="subtitle2" sx={{ color: "rgba(255,255,255,0.92)" }}>
                {title}
              </Typography>
              <Typography variant="h5" sx={{ color: "common.white", fontWeight: 700 }}>
                {value ?? "-"}
              </Typography>
            </Box>

            <Box
              sx={{
                width: 56,
                height: 56,
                borderRadius: 2,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                bgcolor: "rgba(255,255,255,0.12)",
              }}
            >
              {renderIcon()}
            </Box>
          </Box>
        </CardContent>
      </Box>
    </Card>
  );
}
