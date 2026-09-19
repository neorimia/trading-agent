import { definePreset } from '@primeuix/themes';
import Nora from '@primeuix/themes/nora';

/** Nora Noir mapped onto the existing cockpit surfaces. Dark-only. */
export const ConsolePreset = definePreset(Nora, {
  primitive: {
    borderRadius: {
      none: '0',
      xs: '0',
      sm: '2px',
      md: '2px',
      lg: '2px',
      xl: '2px',
    },
  },
  semantic: {
    primary: {
      50: '{zinc.50}',
      100: '{zinc.100}',
      200: '{zinc.200}',
      300: '{zinc.300}',
      400: '{zinc.400}',
      500: '{zinc.500}',
      600: '{zinc.600}',
      700: '{zinc.700}',
      800: '{zinc.800}',
      900: '{zinc.900}',
      950: '{zinc.950}',
    },
    focusRing: {
      width: '2px',
      style: 'solid',
      color: '{zinc.200}',
      offset: '2px',
    },
    formField: {
      borderRadius: '0',
    },
    overlay: {
      modal: {
        borderRadius: '0',
      },
      select: {
        borderRadius: '0',
      },
    },
    colorScheme: {
      dark: {
        primary: {
          color: '{zinc.50}',
          contrastColor: '{zinc.950}',
          hoverColor: '{zinc.100}',
          activeColor: '{zinc.200}',
        },
        highlight: {
          background: 'rgba(230, 232, 238, 0.14)',
          focusBackground: 'rgba(230, 232, 238, 0.22)',
          color: '{zinc.50}',
          focusColor: '{zinc.50}',
        },
        surface: {
          0: '#e6e8ee',
          50: '#c8cdd6',
          100: '#8b909c',
          200: '#6b717c',
          300: '#4a4f58',
          400: '#2c3038',
          500: '#23262e',
          600: '#1b1e25',
          700: '#16181d',
          800: '#12141a',
          900: '#0e1014',
          950: '#0a0c10',
        },
        text: {
          color: '#e6e8ee',
          mutedColor: '#8b909c',
        },
      },
    },
  },
});
