import {
  Box,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  List,
  ListItem,
  ListItemText,
  Stack,
  Typography,
  Button,
} from '@mui/material'

export function SignalStrategyHelpDialog({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>How to create a Strategy (DSL V3)</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            A Strategy is a reusable, versioned bundle of DSL expressions. You define optional inputs (parameters),
            optional variables (aliases), and one or more outputs. Outputs can be used in Alerts/Screener (SIGNAL)
            and in Dashboard plots (OVERLAY).
          </Typography>

          <Divider />

          <Box>
            <Typography variant="subtitle1">Top fields</Typography>
            <List dense>
              <ListItem>
                <ListItemText
                  primary="Name"
                  secondary="Human-friendly unique name within the chosen scope (USER/GLOBAL). Used everywhere you select a saved strategy."
                />
              </ListItem>
              <ListItem>
                <ListItemText
                  primary="Scope"
                  secondary="USER = private to your SigmaTrader account. GLOBAL = template visible to all users (admin/ops use)."
                />
              </ListItem>
              <ListItem>
                <ListItemText
                  primary="Description"
                  secondary="Optional notes explaining the intent, assumptions, and when the strategy works best."
                />
              </ListItem>
              <ListItem>
                <ListItemText
                  primary="Tags"
                  secondary="Free-form comma-separated labels used for searching/filtering (e.g., momentum, mean-reversion, breakout)."
                />
              </ListItem>
              <ListItem>
                <ListItemText
                  primary="Regimes"
                  secondary="Categorize where the strategy fits (e.g., BULL/BEAR/SIDEWAYS) and trading style (e.g., SWING_TRADING, DAY_TRADING). You can add new regimes by typing them."
                />
              </ListItem>
              <ListItem>
                <ListItemText
                  primary="Enabled"
                  secondary="If disabled, the latest version is not selectable for new alerts/screeners. (Existing alerts keep their pinned version.)"
                />
              </ListItem>
            </List>
          </Box>

          <Divider />

          <Box>
            <Typography variant="subtitle1">Inputs (parameters)</Typography>
            <Typography variant="body2" color="text.secondary">
              Inputs make strategies reusable. Each input becomes an identifier you can reference in the output DSL.
              Identifiers are case-insensitive; internally we treat them as uppercase.
            </Typography>
            <List dense>
              <ListItem>
                <ListItemText
                  primary="Name"
                  secondary="The identifier used inside DSL (e.g., FAST, SLOW, TF). Avoid names that collide with metrics/functions (e.g., CLOSE, SMA)."
                />
              </ListItem>
              <ListItem>
                <ListItemText
                  primary="Type"
                  secondary="Controls UI rendering and basic validation/coercion: number/string/bool/enum/timeframe."
                />
              </ListItem>
              <ListItem>
                <ListItemText
                  primary="Default"
                  secondary="Used when you don’t provide overrides in an Alert/Screener/Dashboard."
                />
              </ListItem>
            </List>
          </Box>

          <Divider />

          <Box>
            <Typography variant="subtitle1">Variables</Typography>
            <Typography variant="body2" color="text.secondary">
              Variables are aliases to keep outputs readable and to avoid repeating expressions.
              They behave like the Variables section in Alerts/Screener DSL.
            </Typography>
            <List dense>
              <ListItem>
                <ListItemText
                  primary="Name"
                  secondary="Alias identifier (e.g., RSI_1D_14). Use descriptive names; avoid collisions with metrics/functions."
                />
              </ListItem>
              <ListItem>
                <ListItemText
                  primary="DSL"
                  secondary={'The expression assigned to the alias (e.g., RSI(close, 14, "1d")).'}
                />
              </ListItem>
            </List>
          </Box>

          <Divider />

          <Box>
            <Typography variant="subtitle1">Outputs</Typography>
            <Typography variant="body2" color="text.secondary">
              Outputs are the actual “signals” or “series” you want to reuse.
              A strategy can have multiple outputs; Alerts/Screener typically use SIGNAL outputs and Dashboard uses
              OVERLAY outputs (numeric series).
            </Typography>
            <List dense>
              <ListItem>
                <ListItemText
                  primary="Output name"
                  secondary="Used when selecting which output to apply (e.g., signal, entry, exit, overlay_fast)."
                />
              </ListItem>
              <ListItem>
                <ListItemText
                  primary="Kind: SIGNAL"
                  secondary="Must be a boolean expression (e.g., SMA(close, FAST, TF) > SMA(close, SLOW, TF)). Used for Alerts/Screener matching."
                />
              </ListItem>
              <ListItem>
                <ListItemText
                  primary="Kind: OVERLAY"
                  secondary="Must be numeric (e.g., SMA(close, FAST, TF)). Used for dashboard plots/overlays."
                />
              </ListItem>
              <ListItem>
                <ListItemText
                  primary="DSL"
                  secondary="The expression itself. Any identifier not recognized as a metric/function must be declared as an Input or Variable."
                />
              </ListItem>
              <ListItem>
                <ListItemText
                  primary="Plot (optional)"
                  secondary="A non-binding hint for where to render overlays (e.g., price vs separate pane)."
                />
              </ListItem>
            </List>
          </Box>

          <Divider />

          <Box>
            <Typography variant="subtitle1">Quick examples</Typography>
            <Typography variant="body2" color="text.secondary">
              Bullish crossover (SIGNAL):
            </Typography>
            <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
              SMA(close, FAST, TF) &gt; SMA(close, SLOW, TF) AND RSI(close, RSI_LEN, TF) &gt; RSI_MIN
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              Overlay lines (OVERLAY):
            </Typography>
            <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
              SMA(close, FAST, TF)
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              For DSL function reference, use the in-app DSL help dialogs (Indicators/DSL help) or the docs:
              {' '}
              <Typography component="span" sx={{ fontFamily: 'monospace' }}>
                docs/DSL_improvement.md
              </Typography>
            </Typography>
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  )
}
