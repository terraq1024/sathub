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

// 商务风格主题：窄行高、克制圆角、层级分明的边框与阴影。
// 颜色全部沿用 FRONTEND_THEME_GUIDE.md 的令牌。
const theme: ThemeConfig = {
  token: {
    colorPrimary: '#3f6ff2',
    colorInfo: '#3f6ff2',
    colorSuccess: '#18a999',
    colorWarning: '#e09b3d',
    colorError: '#d95d5d',
    colorText: '#24324a',
    colorTextSecondary: '#5d6b82',
    colorTextTertiary: '#8f9cb0',
    colorBgLayout: '#f0f3f8',
    colorBgContainer: '#ffffff',
    colorBgElevated: '#ffffff',
    colorBorder: '#dce4f0',
    colorBorderSecondary: '#e8edf5',
    colorFillAlter: '#f6f8fc',
    borderRadius: 6,
    controlHeight: 32,
    fontSize: 13,
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", "HarmonyOS Sans SC", sans-serif',
    boxShadow: '0 1px 2px rgba(23, 43, 84, 0.04), 0 4px 16px rgba(23, 43, 84, 0.08)',
    boxShadowSecondary: '0 6px 24px rgba(23, 43, 84, 0.14)'
  },
  components: {
    Layout: {
      bodyBg: '#f0f3f8',
      headerBg: '#ffffff',
      headerHeight: 60
    },
    Menu: {
      itemBg: '#ffffff',
      itemColor: '#5d6b82',
      itemHoverColor: '#3f6ff2',
      itemHoverBg: '#f2f6ff',
      itemSelectedColor: '#3f6ff2',
      itemSelectedBg: '#eef3fe',
      activeBarHeight: 0,
      horizontalItemSelectedColor: '#2f5fe0'
    },
    Table: {
      headerBg: '#f7f9fd',
      headerColor: '#5d6b82',
      headerSplitColor: '#eef2f8',
      rowHoverBg: '#f4f8ff',
      cellPaddingBlock: 8,
      cellPaddingInline: 14,
      headerBorderRadius: 6,
      fontSize: 13
    },
    Tabs: {
      itemColor: '#5d6b82',
      itemSelectedColor: '#2f5fe0',
      itemHoverColor: '#3f6ff2',
      inkBarColor: '#2f5fe0',
      horizontalItemPadding: '10px 4px',
      horizontalMargin: '0 22px 0 0'
    },
    Card: {
      borderRadiusLG: 8,
      paddingLG: 18,
      headerFontSize: 14
    },
    Button: {
      primaryShadow: '0 2px 8px rgba(47, 95, 224, 0.28)',
      defaultShadow: '0 1px 2px rgba(23, 43, 84, 0.05)',
      fontWeight: 500
    },
    Drawer: {
      paddingLG: 20
    },
    Modal: {
      titleFontSize: 15
    },
    Segmented: {
      itemSelectedBg: '#ffffff',
      itemSelectedColor: '#24324a',
      trackBg: '#eef1f7'
    },
    Descriptions: {
      titleColor: '#5d6b82'
    },
    Tag: {
      borderRadiusSM: 4
    },
    Input: {
      activeShadow: '0 0 0 2px rgba(63, 111, 242, 0.12)'
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
