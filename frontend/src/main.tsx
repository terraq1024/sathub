import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigProvider, App as AntApp, ThemeConfig } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
import 'antd/dist/reset.css';
import 'leaflet/dist/leaflet.css';
import './styles.css';
import App from './App';

dayjs.locale('zh-cn');

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false
    }
  }
});

// 去掉全局 darkAlgorithm——深色只用于 CTA 与个别强调块，页面主体是亮色。
const skyfi = {
  pageBg: '#fafafa',
  surface: '#ffffff',
  surfaceWarm: '#f5f5f4',
  ink: '#09090b',
  chromeText: '#e4e4e7',
  chromeTextMuted: '#a1a1aa',
  text: '#18181b',
  textSecondary: '#52525b',
  textTertiary: '#a1a1aa',
  border: '#e4e4e7',
  borderSoft: '#f0f0f2',
  accent: '#fedf84',
  accentDeep: '#eaa71b',
  accentSoft: 'rgba(254, 223, 132, 0.35)',
  accentBg: 'rgba(254, 223, 132, 0.16)',
  success: '#16a34a',
  warning: '#eaa71b',
  error: '#dc2626',
  info: '#4299e1'
};

const theme: ThemeConfig = {
  token: {
    colorPrimary: skyfi.ink,
    colorInfo: skyfi.info,
    colorLink: skyfi.ink,
    colorLinkHover: '#3f3f46',
    colorSuccess: skyfi.success,
    colorWarning: skyfi.warning,
    colorError: skyfi.error,
    colorTextBase: skyfi.ink,
    colorBgBase: skyfi.pageBg,
    colorText: skyfi.text,
    colorTextSecondary: skyfi.textSecondary,
    colorTextTertiary: skyfi.textTertiary,
    colorBgLayout: skyfi.pageBg,
    colorBgContainer: skyfi.surface,
    colorBgElevated: skyfi.surface,
    colorBorder: skyfi.border,
    colorBorderSecondary: skyfi.borderSoft,
    colorFillAlter: '#fafafa',
    colorFillSecondary: 'rgba(9, 9, 11, 0.04)',
    colorFillTertiary: 'rgba(9, 9, 11, 0.06)',
    colorFillQuaternary: 'rgba(9, 9, 11, 0.03)',
    borderRadius: 8,
    borderRadiusSM: 6,
    borderRadiusLG: 10,
    controlHeight: 34,
    fontSize: 14,
    fontFamily:
      'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
    fontWeightStrong: 600,
    boxShadow: 'rgba(9, 9, 11, 0.08) 0px 1px 2px 0px, rgba(9, 9, 11, 0.04) 0px 0px 0px 1px',
    boxShadowSecondary: 'rgba(9, 9, 11, 0.12) 0px 8px 24px 0px'
  },
  components: {
    Layout: {
      bodyBg: skyfi.pageBg,
      // 黑色壳层：全局顶栏用近黑，内容区保持白色（SkyFi 黑框白内容）
      headerBg: skyfi.ink,
      headerHeight: 60
    },
    Menu: {
      // 顶栏菜单在黑色壳层上：灰字、悬停变亮、选中为金色胶囊
      itemBg: 'transparent',
      itemColor: skyfi.chromeTextMuted,
      itemHoverColor: '#fafafa',
      itemHoverBg: 'rgba(255, 255, 255, 0.08)',
      itemSelectedColor: skyfi.ink,
      itemSelectedBg: skyfi.accent,
      activeBarHeight: 0,
      horizontalItemSelectedColor: skyfi.ink
    },
    Table: {
      headerBg: '#fafafa',
      headerColor: skyfi.textSecondary,
      headerSplitColor: 'transparent',
      rowHoverBg: 'rgba(254, 223, 132, 0.16)',
      borderColor: skyfi.borderSoft,
      cellPaddingBlock: 9,
      cellPaddingInline: 14,
      headerBorderRadius: 8,
      fontSize: 13
    },
    Tabs: {
      itemColor: skyfi.textSecondary,
      itemSelectedColor: skyfi.ink,
      itemHoverColor: skyfi.text,
      inkBarColor: skyfi.ink,
      horizontalItemPadding: '10px 4px',
      horizontalMargin: '0 22px 0 0'
    },
    Card: {
      colorBgContainer: skyfi.surface,
      borderRadiusLG: 10,
      paddingLG: 18,
      headerFontSize: 14
    },
    Button: {
      // SkyFi 招牌：黑色实心 CTA（白底页面上的黑色块），文字必须是白色
      primaryColor: '#ffffff',
      fontWeight: 600,
      primaryShadow: 'none',
      defaultShadow: 'none'
    },
    Drawer: {
      colorBgElevated: skyfi.surface,
      paddingLG: 20
    },
    Modal: {
      titleFontSize: 15,
      colorBgElevated: skyfi.surface
    },
    Segmented: {
      itemSelectedBg: skyfi.ink,
      itemSelectedColor: '#ffffff',
      trackBg: skyfi.surfaceWarm
    },
    Descriptions: {
      titleColor: skyfi.textSecondary
    },
    Tag: {
      borderRadiusSM: 6,
      defaultBg: skyfi.surfaceWarm,
      defaultColor: skyfi.text
    },
    Input: {
      colorBgContainer: skyfi.surface,
      activeShadow: '0 0 0 2px rgba(234, 167, 27, 0.18)',
      activeBorderColor: skyfi.accentDeep
    },
    Select: {
      colorBgContainer: skyfi.surface,
      optionSelectedBg: skyfi.surfaceWarm
    },
    DatePicker: {
      colorBgContainer: skyfi.surface,
      cellActiveWithRangeBg: skyfi.surfaceWarm
    },
    Tooltip: {
      colorBgSpotlight: skyfi.ink
    },
    Pagination: {
      itemBg: 'transparent',
      itemActiveBg: skyfi.ink
    },
    Progress: {
      defaultColor: skyfi.accentDeep
    },
    Slider: {
      handleColor: skyfi.ink,
      trackBg: skyfi.ink,
      railBg: skyfi.border,
      railHoverBg: '#d4d4d8'
    },
    Switch: {
      colorPrimary: skyfi.ink
    },
    Empty: {
      colorText: skyfi.textTertiary
    }
  }
};


ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={theme}>
      <AntApp>
        <QueryClientProvider client={queryClient}>
          <App />
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>
);
