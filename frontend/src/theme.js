import { createTheme } from '@mui/material/styles';

const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#00bceb' },
    secondary: { main: '#6cc04a' },
    background: { default: '#0d1117', paper: '#161b22' },
    error: { main: '#f85149' },
    warning: { main: '#d29922' },
    success: { main: '#6cc04a' },
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", sans-serif',
    fontSize: 13,
  },
  components: {
    MuiButton: { defaultProps: { size: 'small' } },
    MuiTextField: { defaultProps: { size: 'small', variant: 'outlined' } },
  },
});

export default theme;
